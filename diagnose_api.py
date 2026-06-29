#!/usr/bin/env python3
"""
诊断 api.198707.xyz 的 HTTPS Read timeout 问题
运行：python3 diagnose_api.py
"""
import os
import sys
import socket
import time
import ssl
import urllib.request
import urllib.error
import subprocess

API_HOST = "api.198707.xyz"
API_BASE = f"https://{API_HOST}"

print("=" * 60)
print(f"{API_HOST} Read Timeout 诊断脚本")
print("=" * 60)

# 1. 环境信息
print("\n[1] 环境信息")
print(f"Python: {sys.version}")
try:
    import requests
    print(f"requests: {requests.__version__}")
except ImportError:
    print("requests: 未安装")
try:
    import urllib3
    print(f"urllib3: {urllib3.__version__}")
except ImportError:
    print("urllib3: 未安装")

# 2. 环境变量（代理）
print("\n[2] 环境变量中的代理设置")
for k in os.environ:
    if "proxy" in k.lower() or "http" in k.lower():
        print(f"  {k}={os.environ[k]}")

# 3. DNS 解析
print("\n[3] DNS 解析结果")
try:
    infos = socket.getaddrinfo(API_HOST, 443)
    for info in infos:
        print(f"  {info}")
except Exception as e:
    print(f"  DNS 失败: {e}")

# 4. 系统 curl 测试
print("\n[4] curl 测试（系统命令）")
for extra in ["", "--http1.1", "--http2", "-4", "-6"]:
    cmd = f"curl -s -o /dev/null -w '%{{http_code}} %{{time_total}}s' --max-time 15 {extra} {API_BASE}"
    try:
        out = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, timeout=20).decode().strip()
        print(f"  curl {extra or '(default)':12s} -> {out}")
    except Exception as e:
        print(f"  curl {extra or '(default)':12s} -> 失败: {e}")

# 5. Python requests 各种方式测试
print("\n[5] Python requests 测试")
if "requests" in sys.modules:
    tests = [
        ("GET 默认", {"method": "get", "url": API_BASE}),
        ("GET 无 headers", {"method": "get", "url": API_BASE, "headers": {}}),
        ("GET 浏览器 UA", {"method": "get", "url": API_BASE, "headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }}),
        ("POST JSON", {"method": "post", "url": API_BASE, "json": {"test": 1}}),
        ("GET /health", {"method": "get", "url": f"{API_BASE}/health"}),
    ]
    for name, kwargs in tests:
        t0 = time.time()
        try:
            method = kwargs.pop("method")
            r = requests.request(method, timeout=(8, 12), **kwargs)
            print(f"  {name:20s} OK {r.status_code} len={len(r.content)} {time.time()-t0:.2f}s")
        except Exception as e:
            print(f"  {name:20s} FAIL {type(e).__name__}: {e} {time.time()-t0:.2f}s")

# 6. Python urllib 原生测试
print("\n[6] Python urllib 原生测试")
t0 = time.time()
try:
    req = urllib.request.Request(API_BASE, headers={"User-Agent": "python-urllib-test"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = resp.read()
        print(f"  urllib OK {resp.status} len={len(data)} {time.time()-t0:.2f}s")
except Exception as e:
    print(f"  urllib FAIL {type(e).__name__}: {e} {time.time()-t0:.2f}s")

# 7. 原始 socket + SSL 测试
print("\n[7] 原始 socket + SSL 测试")
t0 = time.time()
try:
    ctx = ssl.create_default_context()
    with socket.create_connection((API_HOST, 443), timeout=10) as sock:
        with ctx.wrap_socket(sock, server_hostname=API_HOST) as ssock:
            print(f"  SSL 握手成功: {ssock.version()} cipher={ssock.cipher()[0]}")
            ssock.send(f"GET / HTTP/1.1\r\nHost: {API_HOST}\r\nConnection: close\r\n\r\n".encode())
            resp = b""
            while True:
                chunk = ssock.recv(4096)
                if not chunk:
                    break
                resp += chunk
            print(f"  收到响应 {len(resp)} bytes {time.time()-t0:.2f}s")
except Exception as e:
    print(f"  原始 socket FAIL {type(e).__name__}: {e} {time.time()-t0:.2f}s")

# 8. IPv4 / IPv6 强制测试
print("\n[8] 强制 IPv4 / IPv6 测试")
for family, name in [(socket.AF_INET, "IPv4"), (socket.AF_INET6, "IPv6")]:
    t0 = time.time()
    try:
        sock = socket.socket(family, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((API_HOST, 443))
        ctx = ssl.create_default_context()
        ssock = ctx.wrap_socket(sock, server_hostname=API_HOST)
        ssock.send(f"GET / HTTP/1.1\r\nHost: {API_HOST}\r\nConnection: close\r\n\r\n".encode())
        resp = ssock.recv(4096)
        ssock.close()
        print(f"  {name} OK 收到 {len(resp)} bytes {time.time()-t0:.2f}s")
    except Exception as e:
        print(f"  {name} FAIL {type(e).__name__}: {e} {time.time()-t0:.2f}s")

print("\n" + "=" * 60)
print("诊断完成，请把上面的完整输出复制给我。")
print("=" * 60)
