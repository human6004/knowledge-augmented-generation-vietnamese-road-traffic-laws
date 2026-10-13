# Reuse the exact Python 3.10.16 interpreter verified in C4 / D0.1.
FROM spg-registry.us-west-1.cr.aliyuncs.com/spg/openspg-server@sha256:fe6708deef9ebb8da8da7b1cb643e83b827769a5be8811961311639aa1f2cb88
COPY requirements.txt /opt/kag-requirements.txt
RUN python -m venv /opt/kag-venv && /opt/kag-venv/bin/python -m pip install --no-cache-dir --disable-pip-version-check -r /opt/kag-requirements.txt && /opt/kag-venv/bin/python -m pip check
ENV PATH="/opt/kag-venv/bin:${PATH}" PYTHONDONTWRITEBYTECODE=1 KAG_DEBUG_DUMP_CONFIG=0 MPLCONFIGDIR=/tmp/matplotlib
WORKDIR /workspace
ENTRYPOINT ["python", "-B"]
CMD ["-m", "unittest", "discover", "-s", "tests/runtime", "-v"]
