#!/bin/bash

set -e  # Exit on any error

# STEP 1: System dependencies
echo "🔧 Installing system dependencies..."
apt update && apt install -y wget curl git make build-essential \
  libssl-dev zlib1g-dev libbz2-dev libreadline-dev \
  libsqlite3-dev libncursesw5-dev libgdbm-dev liblzma-dev \
  libffi-dev uuid-dev libdb-dev libexpat1-dev \
  libgmp-dev tk-dev

# STEP 2: Install Python 3.10.0
echo "🐍 Installing Python 3.10.0..."
cd /usr/src
wget https://www.python.org/ftp/python/3.10.0/Python-3.10.0.tgz
tar xzf Python-3.10.0.tgz
cd Python-3.10.0
./configure --enable-optimizations
make -j$(nproc)
make altinstall
cd ~

# STEP 3: Clone repo (optional if not already cloned)
if [ ! -d "ai-travel-planner-api" ]; then
  echo "📦 Cloning your Health & Wellness Agents repo..."
  git clone https://github.com/BapanBigData/multi-agents-health-wellness-app.git
fi

cd multi-agents-health-wellness-app

# STEP 4: Set up Python virtual environment
echo "📦 Setting up Python virtual environment..."
python3.10 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# STEP 5: Confirm .env file is present
if [ ! -f ".env" ]; then
  echo "⚠️ .env file not found! Please create one with required API keys before starting the app."
  exit 1
fi

# STEP 6: Start FastAPI server on port 7860 and keep it running
echo "🚀 Starting FastAPI server on port 7860..."
nohup uvicorn app.main:app --host 0.0.0.0 --port 7860 > server.log 2>&1 &
echo "✅ FastAPI server running in background. Check logs with: tail -f server.log"