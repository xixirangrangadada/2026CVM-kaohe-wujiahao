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
    && pip3 install --no-cache-dir supervisor flask

# ---- FlameGraph 工具链（双保险：仓库内置 COPY 优先，缺则 git clone 兜底）----
# 仓库内已带 src/FlameGraph/（stackcollapse-perf.pl + flamegraph.pl，~53KB，离线可用）。
# 若 build context 未提供该目录（例如直接拿 Dockerfile 单文件构建），
# 则构建时从 GitHub 拉取，保证 docker build 零额外步骤即可成。
COPY FlameGraph /opt/FlameGraph
RUN if [ ! -x /opt/FlameGraph/flamegraph.pl ] || [ ! -x /opt/FlameGraph/stackcollapse-perf.pl ]; then \
        rm -rf /opt/FlameGraph && \
        git clone --depth 1 https://github.com/brendangregg/FlameGraph.git /opt/FlameGraph; \
    fi && \
    chmod +x /opt/FlameGraph/*.pl && \
    test -x /opt/FlameGraph/flamegraph.pl && test -x /opt/FlameGraph/stackcollapse-perf.pl

# ---- profiler 应用（常变，置后）----
COPY profiler /opt/app/profiler
COPY web /opt/app/web
COPY supervisord.conf /etc/supervisord.conf

# ---- 运行环境（配置化，docker run -e 可覆盖）----
ENV PYTHONPATH=/opt/app \
    FLAMEGRAPH_DIR=/opt/FlameGraph \
    DATA_DIR=/data/perf \
    SVG_DIR=/data/svg \
    ROTATE_SECONDS=60 \
    RETAIN_HOURS=24 \
    SAMPLE_FREQ=99 \
    TZ=Asia/Shanghai \
    WEB_DIR=/opt/app/web

VOLUME ["/data"]
EXPOSE 8080

# supervisord 前台（PID 1），管 collector + janitor + server
CMD ["supervisord", "-n", "-c", "/etc/supervisord.conf"]
