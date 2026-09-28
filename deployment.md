# Deployment Guide for Stock Monitoring Dashboard (Streamlit)

## 1. Local Development
```bash
# Clone / navigate to the project directory
cd "c:/workspace/Stockmarket prediction model"

# (Optional) Create a virtual environment
python -m venv venv
venv\Scripts\activate  # Windows PowerShell

# Install dependencies
pip install -r requirements.txt

# Run the app locally
streamlit run app.py
```

## 2. Deploy to Streamlit Community Cloud (Streamlit Sharing)
1. **Push the code to a public Git repository** (GitHub, GitLab, or Bitbucket).
2. Sign in to https://share.streamlit.io/ with your GitHub account.
3. Click **"New app"** and select the repository and branch.
4. Set the **Main file path** to `app.py`.
5. Add the **Requirements** (the `requirements.txt` file will be auto‑detected). If you need additional packages, edit the file and push the changes.
6. Click **Deploy** – Streamlit will build the environment, install the dependencies, and launch the app.

## 3. Docker Deployment (Self‑Hosted)
Create a `Dockerfile` in the project root:
```Dockerfile
# Use the official lightweight Python image.
FROM python:3.11-slim

# Set a working directory.
WORKDIR /app

# Copy only the necessary files.
COPY requirements.txt .
COPY app.py .
COPY data_fetcher.py .
COPY alert_utils.py .

# Install dependencies.
RUN pip install --no-cache-dir -r requirements.txt

# Expose the default Streamlit port.
EXPOSE 8501

# Run the Streamlit app.
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.headless=true"]
```
Build and run the container:
```bash
# Build the image (replace <tag> as desired)
docker build -t stock-monitor:latest .

# Run the container
docker run -p 8501:8501 stock-monitor:latest
```
Visit `http://localhost:8501` to view the dashboard.

## 4. Production‑grade Deployment (e.g., Azure App Service, AWS Elastic Beanstalk)
- Use the **Docker** approach above and deploy the container to your chosen service.
- Ensure the service forwards port **8501**.
- Set environment variables if you need to hide API keys (not required for yfinance).

## 5. Continuous Integration (Optional)
Add a simple GitHub Actions workflow (`.github/workflows/deploy.yml`) to automatically build and push a Docker image on every push:
```yaml
name: Build & Push Docker Image

on:
  push:
    branches: [ main ]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up QEMU
        uses: docker/setup-qemu-action@v3
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      - name: Login to DockerHub
        uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}
      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          push: true
          tags: ${{ secrets.DOCKERHUB_USERNAME }}/stock-monitor:latest
```
Replace the secrets with your Docker Hub credentials.

---
**Note**: The dashboard uses only public data from Yahoo Finance, so no API keys are required.
