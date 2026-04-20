#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -f "/etc/os-release" ]]; then
  echo "Cannot verify operating system (missing /etc/os-release)."
  exit 1
fi

if ! grep -qi "ubuntu" /etc/os-release; then
  echo "This installer is intended for Ubuntu servers."
  exit 1
fi

SUDO=""
if [[ "${EUID}" -ne 0 ]]; then
  if command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
  else
    echo "Please run this script as root or install sudo."
    exit 1
  fi
fi

echo "Installing Ubuntu system packages..."
$SUDO apt-get update
$SUDO apt-get install -y \
  python3 \
  python3-venv \
  python3-pip \
  python3-dev \
  build-essential \
  ffmpeg \
  tmux \
  nodejs \
  npm

VENV_DIR="${REPO_ROOT}/.venv"
if [[ ! -d "${VENV_DIR}" ]]; then
  echo "Creating virtual environment in ${VENV_DIR}..."
  python3 -m venv "${VENV_DIR}"
fi

PIP_BIN="${VENV_DIR}/bin/pip"
echo "Upgrading pip/setuptools/wheel..."
"${PIP_BIN}" install --upgrade pip setuptools wheel

REQUIREMENT_FILES=(
  "${REPO_ROOT}/requirements.txt"
  "${REPO_ROOT}/apollo/requirements.txt"
  "${REPO_ROOT}/minerva/requirements.txt"
  "${REPO_ROOT}/demeter/requirements.txt"
  "${REPO_ROOT}/eleuthia/requirements.txt"
)

for req in "${REQUIREMENT_FILES[@]}"; do
  if [[ -f "${req}" ]]; then
    echo "Installing Python dependencies from ${req}..."
    "${PIP_BIN}" install -r "${req}"
  fi
done

if [[ -f "${REPO_ROOT}/eleuthia/package.json" ]]; then
  echo "Installing Node.js dependency for Eleuthia..."
  (cd "${REPO_ROOT}/eleuthia" && npm install)
fi

echo "Done. Activate environment with:"
echo "source ${VENV_DIR}/bin/activate"
