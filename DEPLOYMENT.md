# UAV System Deployment Guide

This guide covers various deployment scenarios for the Constraint-Aware Fault-Tolerant Multi-Agent UAV System.

## Table of Contents

1. [Development Environment](#development-environment)
2. [Demo/Presentation Deployment](#demopresentation-deployment)
3. [Production-Like Deployment](#production-like-deployment)
4. [Docker Deployment](#docker-deployment)
5. [Cloud Deployment](#cloud-deployment)
6. [Raspberry Pi / Edge Deployment](#raspberry-pi--edge-deployment)

---

## Development Environment

### Local Development with uv

**Prerequisites:**
- Python 3.8+
- uv package manager

**Setup:**
```bash
# Clone repository
git clone <your-repo-url>
cd uav_system

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies (creates .venv automatically)
uv sync --group dev

# Activate virtual environment
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate     # Windows
```

**Running:**
```bash
# Dashboard only (for quick demos)
uv run python run_dashboard.py

# Full system with GUI
uv run python launch_with_gui.py

# Full system programmatic
uv run python launch.py
```

**Development Workflow:**
```bash
# Run tests
uv run pytest

# Format code
uv run black .

# Lint code
uv run ruff check .
```

---

## Demo/Presentation Deployment

Perfect for thesis defense, conferences, or demonstrations.

### Quick Demo Setup (Dashboard Only)

```bash
# 1. Install minimal dependencies
uv sync

# 2. Run dashboard
uv run python run_dashboard.py

# 3. Open browser
# Navigate to: http://localhost:8085
```

**Advantages:**
- Fastest startup (~2 seconds)
- No backend dependencies
- Works on any machine with Python
- Ideal for presentations with limited time

### Full Demo Setup (With Backend)

```bash
# Terminal 1: Start GCS
uv run python -m gcs.main

# Terminal 2-6: Start UAVs (in separate terminals)
uv run python -m uav.client 1 0 0 10
uv run python -m uav.client 2 20 0 10
uv run python -m uav.client 3 40 0 10
uv run python -m uav.client 4 0 20 10
uv run python -m uav.client 5 20 20 10

# Terminal 7: Start dashboard
uv run python run_dashboard.py
```

**Advantages:**
- Full OODA loop demonstration
- Real telemetry data
- Realistic failure scenarios

---

## Production-Like Deployment

### Using systemd Services (Linux)

Create service files for each component:

**1. GCS Service (`/etc/systemd/system/uav-gcs.service`):**
```ini
[Unit]
Description=UAV Ground Control Station
After=network.target

[Service]
Type=simple
User=uav
WorkingDirectory=/opt/uav_system
Environment="PATH=/home/uav/.local/bin:/usr/bin"
ExecStart=/home/uav/.local/bin/uv run python -m gcs.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**2. UAV Client Service Template (`/etc/systemd/system/uav-client@.service`):**
```ini
[Unit]
Description=UAV Client %i
After=network.target uav-gcs.service

[Service]
Type=simple
User=uav
WorkingDirectory=/opt/uav_system
Environment="PATH=/home/uav/.local/bin:/usr/bin"
ExecStart=/home/uav/.local/bin/uv run python -m uav.client %i 0 0 10
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**3. Dashboard Service (`/etc/systemd/system/uav-dashboard.service`):**
```ini
[Unit]
Description=UAV Web Dashboard
After=network.target uav-gcs.service

[Service]
Type=simple
User=uav
WorkingDirectory=/opt/uav_system
Environment="PATH=/home/uav/.local/bin:/usr/bin"
ExecStart=/home/uav/.local/bin/uv run python run_dashboard.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Deployment:**
```bash
# Install system
sudo cp -r uav_system /opt/
cd /opt/uav_system
sudo chown -R uav:uav .

# As uav user, install dependencies
uv sync

# Enable and start services
sudo systemctl enable uav-gcs uav-dashboard
sudo systemctl enable uav-client@{1..5}

sudo systemctl start uav-gcs
sudo systemctl start uav-client@{1..5}
sudo systemctl start uav-dashboard

# Check status
sudo systemctl status uav-gcs uav-dashboard
```

---

## Docker Deployment

### Single Container (Dashboard Only)

**Dockerfile:**
```dockerfile
FROM python:3.11-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml uv.lock ./
COPY . .

# Install dependencies
RUN uv sync --frozen --no-dev

# Expose port
EXPOSE 8085

# Run dashboard
CMD ["uv", "run", "python", "run_dashboard.py"]
```

**Build and run:**
```bash
docker build -t uav-system .
docker run -p 8085:8085 uav-system
```

### Multi-Container Setup (Full System)

**docker-compose.yml:**
```yaml
version: '3.8'

services:
  gcs:
    build: .
    command: uv run python -m gcs.main
    networks:
      - uav-network
    ports:
      - "5555:5555"

  uav-1:
    build: .
    command: uv run python -m uav.client 1 0 0 10
    depends_on:
      - gcs
    networks:
      - uav-network

  uav-2:
    build: .
    command: uv run python -m uav.client 2 20 0 10
    depends_on:
      - gcs
    networks:
      - uav-network

  uav-3:
    build: .
    command: uv run python -m uav.client 3 40 0 10
    depends_on:
      - gcs
    networks:
      - uav-network

  dashboard:
    build: .
    command: uv run python run_dashboard.py
    depends_on:
      - gcs
    ports:
      - "8085:8085"
    networks:
      - uav-network

networks:
  uav-network:
    driver: bridge
```

**Run:**
```bash
docker-compose up -d
docker-compose logs -f
docker-compose down
```

---

## Cloud Deployment

### AWS EC2 Deployment

**1. Launch EC2 Instance:**
- AMI: Ubuntu 22.04 LTS
- Instance Type: t3.medium (2 vCPU, 4GB RAM)
- Security Group: Open ports 8085, 5555

**2. Setup:**
```bash
# SSH into instance
ssh -i your-key.pem ubuntu@your-ec2-ip

# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y python3-pip git

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.cargo/env

# Clone and setup
git clone <your-repo>
cd uav_system
uv sync

# Run with screen/tmux for persistence
screen -S uav-dashboard
uv run python run_dashboard.py
# Detach with Ctrl+A, D
```

**3. (Optional) Setup nginx reverse proxy:**
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8085;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

### Google Cloud Run (Containerized)

**cloudbuild.yaml:**
```yaml
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', 'gcr.io/$PROJECT_ID/uav-system', '.']
  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', 'gcr.io/$PROJECT_ID/uav-system']
  - name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
    entrypoint: gcloud
    args:
      - 'run'
      - 'deploy'
      - 'uav-system'
      - '--image'
      - 'gcr.io/$PROJECT_ID/uav-system'
      - '--region'
      - 'us-central1'
      - '--platform'
      - 'managed'
      - '--allow-unauthenticated'
```

**Deploy:**
```bash
gcloud builds submit --config cloudbuild.yaml
```

---

## Raspberry Pi / Edge Deployment

Perfect for on-site demonstrations or embedded GCS.

### Hardware Requirements
- Raspberry Pi 4 (4GB+ RAM recommended)
- microSD card (32GB+)
- Network connectivity

### Setup

**1. Prepare Raspberry Pi:**
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y python3-pip python3-venv git

# Install uv (ARM64 compatible)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**2. Install UAV System:**
```bash
cd ~
git clone <your-repo>
cd uav_system

# Install with uv
uv sync

# Optional: Install only required deps to save space
uv sync --no-dev
```

**3. Auto-start on Boot:**

Create `/etc/rc.local`:
```bash
#!/bin/bash
cd /home/pi/uav_system
/home/pi/.local/bin/uv run python run_dashboard.py &
exit 0
```

```bash
sudo chmod +x /etc/rc.local
```

**4. (Optional) Kiosk Mode for Touch Screen:**
```bash
# Install chromium
sudo apt install -y chromium-browser unclutter

# Edit autostart
nano ~/.config/lxsession/LXDE-pi/autostart

# Add:
@chromium-browser --kiosk --noerrdialogs --disable-infobars http://localhost:8085
@unclutter -idle 0
```

---

## Deployment Comparison

| Scenario | Best For | Setup Time | Reproducibility | Resource Usage |
|----------|----------|------------|-----------------|----------------|
| **Dev Local** | Development, testing | 2 min | High (uv.lock) | Low |
| **Demo Dashboard** | Quick presentations | 30 sec | High | Minimal |
| **systemd** | Long-running servers | 15 min | High | Medium |
| **Docker** | Isolated environments | 5 min | Very High | Medium |
| **Cloud (EC2)** | Remote access | 10 min | High | Variable |
| **Cloud (Run)** | Serverless, scalable | 5 min | Very High | Auto-scaled |
| **Raspberry Pi** | Embedded/portable GCS | 20 min | High | Low |

---

## Environment Variables

For production deployments, configure via environment variables:

```bash
# GCS Configuration
export UAV_GCS_HOST=0.0.0.0
export UAV_GCS_PORT=5555

# Dashboard Configuration
export UAV_DASHBOARD_PORT=8085
export UAV_DASHBOARD_HOST=0.0.0.0

# Mission Configuration
export UAV_MISSION_FILE=missions/test_scenario.yaml

# Logging
export UAV_LOG_LEVEL=INFO
export UAV_LOG_FILE=/var/log/uav/system.log
```

---

## Backup and Reproducibility

### Exporting Exact Environment

```bash
# Export installed packages (uv.lock already handles this)
uv export --format requirements-txt > requirements.freeze.txt

# Backup configuration
tar -czf uav-config-backup.tar.gz config/ missions/

# Full system backup
tar -czf uav-system-$(date +%Y%m%d).tar.gz \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='.git' \
  .
```

### Restoring on New Machine

```bash
# Method 1: Using uv.lock (recommended)
git clone <repo>
cd uav_system
uv sync --frozen  # Uses exact versions from lockfile

# Method 2: Using frozen requirements
uv pip install -r requirements.freeze.txt
```

---

## Monitoring and Logging

### Production Logging Setup

```bash
# Create log directory
sudo mkdir -p /var/log/uav
sudo chown uav:uav /var/log/uav

# Configure log rotation
sudo tee /etc/logrotate.d/uav <<EOF
/var/log/uav/*.log {
    daily
    rotate 7
    compress
    delaycompress
    notifempty
    create 0644 uav uav
}
EOF
```

### Health Checks

```bash
# Simple health check script
#!/bin/bash
curl -f http://localhost:8085 || systemctl restart uav-dashboard
curl -f http://localhost:5555 || systemctl restart uav-gcs
```

---

## Troubleshooting

### Common Issues

**Port already in use:**
```bash
# Find process using port
lsof -i :8085
# Kill if needed
kill -9 <PID>
```

**Permission denied:**
```bash
# Fix uv permissions
chmod +x ~/.local/bin/uv
```

**Missing dependencies:**
```bash
# Reinstall from lockfile
uv sync --reinstall
```

**Network connectivity (Docker):**
```bash
# Check container networking
docker network inspect uav-network
```

**uv build error ("Unable to determine which files to ship"):**
```bash
# Ensure pyproject.toml has package configuration
# Should include:
# [tool.hatch.build.targets.wheel]
# packages = ["uav", "gcs", "visualization", "missions"]

# Then retry
uv sync
```

---

## Security Considerations

### Production Hardening

1. **Firewall Configuration:**
```bash
sudo ufw allow 8085/tcp  # Dashboard
sudo ufw allow 5555/tcp  # GCS
sudo ufw enable
```

2. **Reverse Proxy with SSL (nginx + certbot):**
```bash
sudo apt install -y nginx certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com
```

3. **Environment Isolation:**
- Always use virtual environments
- Use `uv sync --frozen` in production
- Don't run as root user

4. **Secrets Management:**
```bash
# Don't commit secrets
echo "*.env" >> .gitignore
echo "secrets/" >> .gitignore

# Use environment variables
export DATABASE_PASSWORD=$(cat /secure/path/db_password)
```

---

## Performance Tuning

### For Large Fleets (10+ UAVs)

```yaml
# config/gcs_config.yaml
ooda_engine:
  telemetry_rate_hz: 1.0  # Reduce polling frequency

fleet_monitor:
  batch_processing: true
  max_concurrent_uavs: 20
```

### For Resource-Constrained Environments

```bash
# Use minimal dependencies
uv sync --no-dev

# Disable matplotlib backend for headless servers
export MPLBACKEND=Agg
```

---

## Next Steps

After deployment:
1. Test all failure scenarios
2. Run load testing (simulate multiple UAVs)
3. Set up monitoring/alerting
4. Document your specific configuration
5. Create runbooks for common operations

For questions or issues, refer to the main README.md or open an issue.
