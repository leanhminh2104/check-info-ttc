# Dùng Python chính thức (3.11) làm base image
FROM python:3.11-slim

# Cài đặt các gói cần thiết
WORKDIR /app

# Copy requirements trước để tối ưu cache
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ code vào container
COPY . .

# Cổng chạy (Vercel không cần expose, nhưng Docker local thì có thể)
EXPOSE 8000

# Chạy uvicorn để expose API (FastAPI/Flask)
# Vì bạn đang dùng BaseHTTPRequestHandler, ta sẽ dùng "python -m http.server" kiểu custom
# Nhưng tốt hơn là dùng một framework web như Flask/FastAPI
# Nếu vẫn muốn giữ code gốc thì chạy thẳng login.py
CMD ["python", "api/login.py"]
