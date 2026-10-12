# devops-nginx-proxy

[![CI - Test and Build](https://github.com/DucLoiNguyen/devops-nginx-proxy/actions/workflows/ci.yml/badge.svg)](https://github.com/DucLoiNguyen/devops-nginx-proxy/actions/workflows/ci.yml)

Dự án thực hành DevOps: đóng gói ứng dụng Flask bằng Docker, đặt **Nginx làm reverse proxy + load balancer** phía trước, và xây dựng **pipeline CI/CD** bằng GitHub Actions để tự động test, build và đẩy image lên GitHub Container Registry (GHCR).

## Mục lục

1. [Tổng quan](#1-tổng-quan)
2. [Kiến trúc và công nghệ](#2-kiến-trúc-và-công-nghệ)
3. [Các vấn đề gặp phải và cách xử lý](#3-các-vấn-đề-gặp-phải-và-cách-xử-lý)
4. [Cấu trúc thư mục](#4-cấu-trúc-thư-mục)
5. [Chạy dự án](#5-chạy-dự-án)
6. [Pipeline CI/CD](#6-pipeline-cicd)
7. [Bài học rút ra](#7-bài-học-rút-ra)
8. [Hướng phát triển](#8-hướng-phát-triển)

---

## 1. Tổng quan

Dự án gồm ba phần nối tiếp nhau:

| Phần | Nội dung |
|---|---|
| Ứng dụng | Web app Flask nhỏ, trả về ID container đang xử lý request, nên nhìn là biết request đi vào bản nào |
| Hạ tầng | Docker + Docker Compose, Nginx reverse proxy chia tải giữa 2 bản app |
| CI/CD | GitHub Actions: chạy test, nếu qua thì build image và đẩy lên GHCR |

**Vì sao cần reverse proxy?** Người dùng chỉ gọi vào Nginx, không gọi thẳng vào app. Nhờ vậy có thể chia tải giữa nhiều bản app, gắn HTTPS tại một chỗ, ẩn app khỏi bên ngoài, thêm header bảo mật và thay app mà không đổi địa chỉ truy cập.

## 2. Kiến trúc và công nghệ

```
Trình duyệt ──► Nginx (cổng 8080) ──► app1 (Flask/gunicorn, 127.0.0.1:5001)
                                  └─► app2 (Flask/gunicorn, 127.0.0.1:5002)
```

Pipeline CI/CD:

```
git push ──► [Job test: pytest] ──pass──► [Job build-and-push] ──► ghcr.io/ducloinguyen/devops-nginx-proxy
                    │
                   fail ──► dừng, không build image
```

**Công nghệ sử dụng:** Python 3.12, Flask, gunicorn, pytest, Docker, Docker Compose, Nginx 1.27, GitHub Actions, GitHub Container Registry, GitHub Codespaces.

## 3. Các vấn đề gặp phải và cách xử lý

Phần này ghi lại các sự cố thật trong quá trình làm, gồm triệu chứng, cách khoanh vùng và kết luận.

### 3.1. Lỗi 504 Gateway Timeout giữa Nginx và app

**Triệu chứng:** mở trang qua Nginx (cổng 8080) thì nhận `504 Gateway Timeout`, dù `docker compose ps` cho thấy cả hai container đều `Up`.

**Ý nghĩa của mã lỗi:** 504 nghĩa là Nginx đã nhận request nhưng khi chuyển tiếp cho app phía sau thì chờ mãi không có phản hồi. Khác với 502 (app chủ động từ chối kết nối), 504 là gói tin đi vào khoảng không. Log của Nginx cũng ghi rõ: `upstream timed out (110: Operation timed out) while connecting to upstream`, tức Nginx không kết nối được tới `172.18.0.2:5000`.

**Các giả thuyết đã đặt ra và loại bỏ:**

| Giả thuyết | Cách kiểm tra | Kết quả |
|---|---|---|
| App bị crash | `docker compose logs app` | Loại: gunicorn đang lắng nghe `0.0.0.0:5000`, worker chạy bình thường |
| Nginx giữ IP cũ của container (Nginx chỉ phân giải tên `app` một lần lúc khởi động) | `docker inspect` so IP | Loại: IP của `app` đúng là `172.18.0.2`, khớp với địa chỉ Nginx đang gọi |
| Xung đột dải IP của mạng Docker | `ip -4 addr` | Loại: không có dải nào trùng nhau |
| Lỗi cấu hình Nginx hoặc Dockerfile | Gọi app từ nhiều điểm khác nhau (bảng dưới) | Loại |

**Phép thử quyết định (thử từng chặng của đường đi):**

| Phép thử | Kết quả | Kết luận |
|---|---|---|
| App tự gọi chính nó (`127.0.0.1:5000` trong container app) | OK | App trả lời đúng |
| Máy chủ (Codespace) gọi thẳng vào `172.18.0.2:5000` | OK | Đường host → container thông |
| Nginx gọi sang `app:5000` | **Timeout** | Đường container → container bị chặn |

**Kết luận:** code, Dockerfile và cấu hình Nginx đều đúng. Lưu lượng giữa hai container trên cùng mạng Docker bị chặn trong môi trường GitHub Codespaces, còn lưu lượng từ host vào container thì thông. **Chưa xác định được cơ chế chặn cụ thể bên trong Codespace**, chỉ chứng minh được *đường nào* bị chặn.

**Cách khắc phục:** đổi cách nối để né đường bị chặn:
- Hai bản app mở cổng ra `127.0.0.1:5001` và `127.0.0.1:5002`
- Nginx chạy với `network_mode: host` và gọi vào hai cổng đó

Cấu hình này đang được dùng trong `docker-compose.yml` và `nginx/nginx.conf` của repo.

**So sánh hai cấu hình:**

| | Cấu hình chuẩn (tên service) | Cấu hình đang dùng (network host) |
|---|---|---|
| Nginx gọi app qua | `app:5000` (DNS nội bộ Docker) | `127.0.0.1:5001` và `127.0.0.1:5002` |
| Cô lập mạng | Tốt hơn, app không mở cổng ra ngoài | Kém hơn, app mở cổng trên localhost |
| Thêm bản app | `--scale app=N` rồi `restart nginx` | Khai báo thêm service và cổng |
| Nên dùng khi | VPS hoặc máy chủ thật | Môi trường như Codespaces có giới hạn mạng giữa container |

Cấu hình chuẩn, dùng khi môi trường không bị giới hạn:

```yaml
services:
  app:
    build: ./app
    restart: unless-stopped

  nginx:
    image: nginx:1.27-alpine
    ports:
      - "8080:80"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - app
    restart: unless-stopped
```

với `upstream flask_app { server app:5000; }` trong `nginx.conf`.

**Lưu ý thêm về cấu hình chuẩn:** Nginx chỉ phân giải tên `app` một lần khi khởi động. Mỗi khi đổi số lượng container `app` (hoặc tạo lại chúng), cần chạy `docker compose restart nginx` để Nginx nhận danh sách địa chỉ mới. Đây là hạn chế của cấu hình Nginx tĩnh, và là lý do trong môi trường lớn người ta dùng công cụ có service discovery như Kubernetes hoặc Traefik.

### 3.2. Lỗi `not found` khi kéo image từ GHCR

**Triệu chứng:** pipeline xanh cả hai job, package đã đặt Public, nhưng lệnh sau báo lỗi:

```
docker: Error response from daemon: failed to resolve reference
"ghcr.io/ducloinguyen/devops-nginx-proxy:latest": ... not found
```

**Cách khoanh vùng:**

1. **Loại giả thuyết sai tên:** GHCR yêu cầu tên image viết thường. Workflow đã tự chuyển `DucLoiNguyen` thành `ducloinguyen`, và tên dùng trong lệnh pull đúng.
2. **Kiểm tra image có tồn tại không, không qua Docker:** hỏi thẳng GHCR bằng `curl` theo giao thức registry:

   ```bash
   TOKEN=$(curl -s "https://ghcr.io/token?scope=repository:ducloinguyen/devops-nginx-proxy:pull" \
     | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")
   curl -s -o /dev/null -w "latest -> %{http_code}\n" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.v2+json" \
     https://ghcr.io/v2/ducloinguyen/devops-nginx-proxy/manifests/latest
   ```

   Kết quả `200` chứng minh image tồn tại và đọc được ẩn danh.
3. **Đổi một biến số:** `docker logout ghcr.io` rồi pull lại thì thành công.

**Kết luận:** cùng một image và cùng một lệnh, chỉ đổi danh tính đăng nhập thì kết quả đổi theo. Nguyên nhân khả dĩ nhất là Codespace giữ sẵn thông tin đăng nhập `ghcr.io` không đủ quyền; một khả năng khác là lúc chạy lần đầu, package còn ở chế độ Private và chỉ chuyển Public sau đó. Không thể khẳng định chắc chắn cái nào, nhưng cách xử lý giống nhau.

**Bài học:** `not found` từ registry không đồng nghĩa với "image không tồn tại". Nhiều registry cố tình trả `not found` thay vì `denied` để không lộ việc một package private có tồn tại. Khi gặp lỗi này, kiểm tra cả hai hướng: image có thật không, và mình đang đăng nhập bằng danh tính nào.

### 3.3. Pipeline cần có "bằng chứng" là chặn được code lỗi

Pipeline xanh chưa chứng minh được gì nếu chưa từng thấy nó đỏ. Vì vậy đã cố tình làm hỏng app (đổi chuỗi `Xin chào` thành `Tạm biệt` để test thất bại) và quan sát:

- Job `test` **fail** (đỏ)
- Job `build-and-push` **không chạy**, không có image lỗi nào được đẩy lên GHCR
- Sau khi sửa lại, pipeline xanh trở lại

Ảnh minh họa (thêm vào thư mục `docs/images/`):

| Lần chạy | Ảnh |
|---|---|
| Test thất bại, build bị chặn | `docs/images/ci-fail.png` |
| Sau khi sửa, pipeline thành công | `docs/images/ci-pass.png` |

![CI fail](docs/images/ci-fail.png)
![CI pass](docs/images/ci-pass.png)

### 3.4. Lỗi nhỏ: dán lệnh bị dính chữ

Khi dán khối lệnh nhiều dòng vào terminal, một đoạn thừa bị dính vào cuối dòng lệnh. Lần này vô hại, nhưng lỗi kiểu này có thể làm lệnh chạy sai mà khó nhận ra. Thói quen tốt: đọc lướt lại lệnh trước khi nhấn Enter.

## 4. Cấu trúc thư mục

```
devops-nginx-proxy/
├── .github/workflows/ci.yml   # Pipeline CI/CD
├── app/
│   ├── app.py                 # Ứng dụng Flask
│   ├── test_app.py            # Test bằng pytest
│   ├── requirements.txt
│   └── Dockerfile
├── nginx/
│   └── nginx.conf             # Cấu hình reverse proxy + load balancing
├── docs/images/               # Ảnh minh họa pipeline
├── docker-compose.yml
├── .gitignore
└── README.md
```

## 5. Chạy dự án

**Yêu cầu:** Docker và Docker Compose (hoặc dùng GitHub Codespaces, đã có sẵn).

```bash
git clone https://github.com/DucLoiNguyen/devops-nginx-proxy.git
cd devops-nginx-proxy
docker compose up -d --build
docker compose ps
```

Kiểm tra và xem chia tải (ID container sẽ luân phiên giữa hai giá trị):

```bash
for i in {1..6}; do curl -s http://localhost:8080; done
```

Chạy test:

```bash
pip install -r app/requirements.txt pytest
cd app && pytest -v
```

Dừng và dọn dẹp:

```bash
docker compose down
```

**Chạy trực tiếp image đã build bởi pipeline:**

```bash
docker run --rm -d -p 5000:5000 --name test-ci ghcr.io/ducloinguyen/devops-nginx-proxy:latest
curl http://localhost:5000
docker stop test-ci
```

Nếu gặp `not found`, thử `docker logout ghcr.io` rồi pull lại (xem mục 3.2).

## 6. Pipeline CI/CD

File: `.github/workflows/ci.yml`

| Thành phần | Vai trò |
|---|---|
| Trigger `push` và `pull_request` vào `main` | Mọi thay đổi đều được kiểm tra |
| Job `test` | Cài thư viện, chạy `pytest` |
| `needs: test` | Job build chỉ chạy khi test đã qua |
| `if: github.event_name == 'push'` | Pull Request chỉ chạy test, không đẩy image |
| `secrets.GITHUB_TOKEN` | Token tạm do GitHub cấp cho mỗi lần chạy, không phải lưu mật khẩu nào |
| `permissions: packages: write` | Cho phép workflow ghi image vào GHCR |
| Tag `latest` | Luôn trỏ tới bản mới nhất |
| Tag `sha-<mã commit>` | Gắn image với commit cụ thể, để truy vết và quay về bản cũ |

## 7. Bài học rút ra

1. **Đọc đúng mã lỗi:** 502 và 504 cho biết lỗi nằm ở đâu, nên nhìn mã lỗi trước khi đoán.
2. **Gỡ lỗi theo từng đoạn:** thử từng chặng của đường đi (client → proxy → app) để biết chính xác đoạn nào đứt.
3. **Trạng thái "xanh" không đảm bảo mọi thứ đúng:** container `Up` mà vẫn không giao tiếp được; pipeline xanh mà pull vẫn lỗi. Luôn kiểm tra kết quả thực tế.
4. **Kiểm tra bằng hai công cụ độc lập:** `curl` thấy mà Docker không thấy thì lỗi nằm ở phía Docker.
5. **Môi trường khác nhau cho kết quả khác nhau:** cùng một cấu hình có thể chạy trên máy này mà không chạy trên máy kia.
6. **CI chỉ có giá trị khi từng chứng minh được nó chặn lỗi.**

## 8. Hướng phát triển

- [ ] Thêm HTTPS (chứng chỉ tự ký hoặc Let's Encrypt) và chuyển hướng HTTP sang HTTPS
- [ ] Thêm `healthcheck` cho app, thêm header bảo mật trong Nginx
- [ ] Thêm bước lint (`flake8`) vào pipeline và bật branch protection
- [ ] Deploy tự động lên VPS qua SSH (kéo image từ GHCR, `docker compose up -d`)
- [ ] Giám sát bằng Prometheus + Grafana