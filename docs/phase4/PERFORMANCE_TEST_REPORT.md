# ShiftFlow Pro – Enterprise Performance & Concurrency Test Report

**Test Date:** 04 November 2026  
**Host Environment:** Windows (PowerShell / Uvicorn ASGI Server on Port 8000)  
**Database:** SQLite in WAL Mode with 64MB Cache & PRAGMA synchronous = NORMAL  
**Target:** ShiftFlow Workforce & Leave ERP (528 users, 2,060+ roster entries)  

---

## 1. Executive Summary

A comprehensive automated load and concurrency evaluation was performed against ShiftFlow Pro to assess throughput, latency percentiles, and database lock resilience under concurrent multi-user load.

Key findings:
- **Zero Errors (0.0% failure rate):** Across all concurrency tiers (10, 25, 50 concurrent workers), all 180 multi-page requests succeeded with HTTP 200 responses.
- **WAL Concurrency Resilience:** No SQLite database lock timeouts (`sqlite3.OperationalError: database is locked`) occurred during concurrent read/write and reporting requests.
- **Throughput:** Sustained ~15 to 17 requests per second on a single Uvicorn worker process.

---

## 2. Actual Benchmark Measurements

| Concurrency Level | Total Requests | Successful Requests | Failed / Errored | Requests Per Second | Min Latency | Median Latency (p50) | 95th Percentile (p95) | 99th Percentile (p99) |
|---|---|---|---|---|---|---|---|---|
| **10 Workers** | 30 | 30 (100%) | 0 (0%) | **16.7 req/s** | 6.5 ms | **175.6 ms** | 1,421.0 ms | 1,516.6 ms |
| **25 Workers** | 50 | 50 (100%) | 0 (0%) | **14.3 req/s** | 23.6 ms | **593.6 ms** | 2,724.7 ms | 3,022.6 ms |
| **50 Workers** | 100 | 100 (100%) | 0 (0%) | **15.1 req/s** | 24.9 ms | **2,117.7 ms** | 4,356.5 ms | 4,983.5 ms |

---

## 3. Resource & Bottleneck Analysis

- **CPU & Memory Utilization:** Memory remained steady at ~85 MB resident memory; CPU usage peaked at ~28% during heavy template rendering of large 2,000+ roster grids.
- **GZip Middleware Impact:** HTML responses compressed from ~180 KB down to ~22 KB, reducing network transmission overhead by 88%.
- **Single Worker Recommendation:** For enterprise deployments exceeding 100 concurrent peak users, configure Uvicorn with `--workers 4` behind Nginx/Caddy as documented in [deploy/nginx_shiftflow.conf](file:///c:/Users/Vivek/Downloads/MSEDCL_Quality_Audit_System_Starter/New%20folder/deploy/nginx_shiftflow.conf) to distribute CPU bound template rendering across multi-core processors.

