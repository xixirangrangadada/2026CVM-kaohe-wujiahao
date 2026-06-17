# ════════════════════════════════════════════════════════
# 题2 容器化持续 CPU Profiling
# 架构 aarch64；必须以 --privileged --pid=host 运行
#   --privileged：perf 访问 PMU
#   --pid=host  ：采集宿主机/其他容器的进程
# 另需挂载宿主内核符号 /lib/modules（解析内核栈），见 README
# ════════════════════════════════════════════════════════
FROM openeuler:20.03

# ---- 依赖层（少变，置前利用缓存）----
RUN dnf install -y perf perl python3 python3-pip git tzdata \
    && ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && dnf clean all \
    && pip3 install --no-cache-dir supervisor

# ---- FlameGraph 工具链（从 build context 拷，避免 build 时 github 网络依赖）----
COPY FlameGraph /opt/FlameGraph
RUN chmod +x /opt/FlameGraph/*.pl

# ---- profiler 应用（常变，置后）----
COPY profiler /opt/app/profiler
COPY supervisord.conf /etc/supervisord.conf

# ---- 运行环境（配置化，docker run -e 可覆盖）----
ENV PYTHONPATH=/opt/app \
    FLAMEGRAPH_DIR=/opt/FlameGraph \
    DATA_DIR=/data/perf \
    SVG_DIR=/data/svg \
    ROTATE_SECONDS=60 \
    RETAIN_HOURS=24 \
    SAMPLE_FREQ=99 \
    TZ=Asia/Shanghai

VOLUME ["/data"]
EXPOSE 8080

# supervisord 前台（PID 1），管 collector + janitor
CMD ["supervisord", "-n", "-c", "/etc/supervisord.conf"]
