FROM python:3.12-slim
ENV TZ=Asia/Shanghai
WORKDIR /app
COPY requirements.txt .
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple && \
    pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--ws-ping-interval", "20", "--ws-ping-timeout", "30"]
