import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { Page, Button, Card, Progress, Terminal } from "../../admin/ui"
import { Notice, inputClass } from "./shared"
import {
  loadKagStatus,
  loadPipelineStatus,
  loadSampleInspection,
  inspectionError,
} from "./kag-inspection"
import {
  loadBuilderStatus,
  runBuilderAction,
  builderStateLabel,
} from "./kag-inspection"
import type { BuilderStatus } from "./kag-inspection"
import { ApiError } from "../../api"

export function useInspection<T>(load: (signal?: AbortSignal) => Promise<T>) {
  const [value, setValue] = useState<T>(),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [version, setVersion] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError("")
    setValue(undefined)
    load(controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setValue(result)
      })
      .catch((failure) => {
        if (!controller.signal.aborted) setError(inspectionError(failure))
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [load, version])
  return { value, error, loading, reload: () => setVersion((v) => v + 1) }
}

async function loadOverview(signal?: AbortSignal) {
  const status = await loadKagStatus(signal)
  try {
    return {
      status,
      sample: await loadSampleInspection(signal),
      sampleError: "",
    }
  } catch (error) {
    return { status, sample: undefined, sampleError: inspectionError(error) }
  }
}

export function KagOverview() {
  const data = useInspection(loadOverview),
    status = { value: data.value?.status },
    sample = { value: data.value?.sample },
    providers = sample.value?.providers
  return (
    <section className="mt-8 border-t border-line pt-5 min-w-0">
      <div className="flex flex-wrap justify-between gap-3">
        <h2 className="font-semibold">Vận hành KAG SAMPLE</h2>
        <Button disabled={data.loading} onClick={data.reload}>
          Kiểm tra KAG
        </Button>
      </div>
      <Notice {...data} retry={data.reload} />
      <Notice error={data.value?.sampleError} retry={data.reload} />
      {status.value && (
        <dl className="mt-3 text-sm">
          {Object.entries({
            liveness: "API liveness",
            queryReadiness: "Query",
            retrievalReadiness: "Retrieval",
            vectorRetrievalReadiness: "Vector retrieval",
            release: "Release artifact",
          }).map(([key, label]) => {
            const check =
              status.value![(key as keyof NonNullable<typeof status.value>)]
            return (
              <div
                key={key}
                className="flex flex-wrap justify-between gap-3 border-b border-line py-2"
              >
                <dt>{label}</dt>
                <dd>
                  {check.state}
                  {check.code ? ` · ${check.code}` : ""}
                </dd>
              </div>
            )
          })}
        </dl>
      )}
      {sample.value && (
        <div className="mt-4 text-sm space-y-2 break-words">
          <p>Release SAMPLE: {sample.value.release_id}</p>
          <p>
            Backend đã xác minh: {sample.value.backend.database} ·{" "}
            {sample.value.backend.namespace} · READ-ONLY
          </p>
          <p>
            Graph: {sample.value.counts.nodes} node ·{" "}
            {sample.value.counts.edges} cạnh · {sample.value.counts.vectors}{" "}
            vector
          </p>
          <p>Kiểm tra lúc: {sample.value.verified_at}</p>
        </div>
      )}
      {providers && (
        <div className="mt-4 text-sm space-y-2">
          <p>
            Provider: {providers.state} · embedding{" "}
            {providers.attempts?.embedding ?? "Chưa đo"} · chat{" "}
            {providers.attempts?.chat ?? "Chưa đo"} request outbound trong
            ledger.
          </p>
          <p className="break-words">
            Model cấu hình: {providers.configured_chat_model ?? "Chưa cấu hình"}{" "}
            · {providers.configured_embedding_model ?? "Chưa cấu hình"}
          </p>
          <p>
            Upstream/proxy retry: chưa đo. Danh tính backend chính xác: NOT
            VERIFIED. Readiness không gọi provider.
          </p>
          <details>
            <summary className="cursor-pointer underline">
              Request và lỗi gần đây của process hiện tại
            </summary>
            <p className="mt-2">
              Từ: {providers.receipt_window?.since ?? "Chưa có cửa sổ quan sát"}
            </p>
            {providers.receipt_window?.recent.length ? (
              providers.receipt_window.recent.map((r, i) => (
                <p key={i} className="py-2 break-words border-b border-line">
                  {r.timestamp} · {r.kind} · {r.source_component} · {r.outcome}{" "}
                  · HTTP {r.status ?? "—"} · {r.latency_ms ?? "—"} ms · request{" "}
                  {r.request_id ?? "Không có"}
                </p>
              ))
            ) : (
              <p>
                Chưa có request trong cửa sổ này; không chứng minh provider hoạt
                động.
              </p>
            )}
          </details>
        </div>
      )}
      <p className="text-sm mt-4">
        Production WRITE: BLOCKED. Artifact, runtime capability và SAMPLE
        acceptance được kiểm tra riêng.
      </p>
      <Link to="/admin/docker" className="inline-block mt-3 underline">
        Kết nối dịch vụ và kiểm thử Retrieval
      </Link>
    </section>
  )
}

export function Graph() {
  const data = useInspection(loadSampleInspection),
    [query, setQuery] = useState(""),
    [selected, setSelected] = useState("")
  const sample = data.value,
    nodes =
      sample?.nodes.filter((n) =>
        `${n.entity_type} ${n.entity_id} ${n.properties.title ?? n.properties.ten ?? ""}`
          .toLowerCase()
          .includes(query.toLowerCase()),
      ) ?? []
  const node = sample?.nodes.find(
    (n) => JSON.stringify([n.entity_type, n.entity_id]) === selected,
  )
  const relations = node
    ? (sample?.edges.filter(
        (e) =>
          (e.from[0] === node.entity_type && e.from[1] === node.entity_id) ||
          (e.to[0] === node.entity_type && e.to[1] === node.entity_id),
      ) ?? [])
    : []
  return (
    <Page
      title="Đồ thị tri thức"
      subtitle="Đọc graph SAMPLE thực qua broker; kiểm tra fingerprint trước và sau. Không có quyền ghi."
      actions={
        <Button disabled={data.loading} onClick={data.reload}>
          Kiểm tra lại
        </Button>
      }
    >
      <Notice {...data} retry={data.reload} />
      {sample && (
        <>
          <div className="grid sm:grid-cols-3 gap-4 mb-5">
            {[
              ["Nodes", sample.counts.nodes],
              ["Quan hệ", sample.counts.edges],
              ["Vectors", sample.counts.vectors],
            ].map(([label, value]) => (
              <Card key={label} className="p-5">
                <p className="text-xs text-muted">{label}</p>
                <p className="text-3xl font-semibold mt-3">{value}</p>
              </Card>
            ))}
          </div>
          <div className="grid lg:grid-cols-2 gap-5 mb-5">
            {[
              ["Loại node", sample.nodes.map((n) => n.entity_type)],
              ["Loại quan hệ", sample.edges.map((e) => e.predicate)],
            ].map(([title, types]) => (
              <Card key={String(title)} title={String(title)}>
                <div className="px-5 pb-5 space-y-3">
                  {Object.entries(
                    (types as string[]).reduce<Record<string, number>>(
                      (counts, type) => {
                        counts[type] = (counts[type] || 0) + 1
                        return counts
                      },
                      {},
                    ),
                  ).map(([type, count]) => (
                    <div
                      key={type}
                      className="grid grid-cols-[minmax(0,1fr)_60px] gap-3 text-xs"
                    >
                      <div>
                        <p className="break-words mb-1">{type}</p>
                        <Progress
                          value={(count / (types as string[]).length) * 100}
                        />
                      </div>
                      <p className="text-right">{count}</p>
                    </div>
                  ))}
                </div>
              </Card>
            ))}
          </div>
          <div className="py-4 text-sm space-y-2 break-words">
            <p>
              {sample.counts.nodes} node · {sample.counts.edges} cạnh ·{" "}
              {sample.counts.vectors} vector · READ-ONLY
            </p>
            <p>
              {sample.backend.database} · {sample.backend.namespace} · backend
              đã xác minh lúc {sample.verified_at}
            </p>
            <p>
              Database ID: {sample.backend.database_id} · Server ID:{" "}
              {sample.backend.server_id}
            </p>
            <p className="break-all">Fingerprint: {sample.graph_fingerprint}</p>
            <p>Release: {sample.release_id}</p>
          </div>
          <label className="block text-sm">
            Tìm node theo mã hoặc tên
            <input
              className={`${inputClass} mt-2`}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <div className="grid lg:grid-cols-[minmax(0,1fr)_minmax(0,360px)] gap-5 mt-5 min-w-0">
            <div
              className="max-h-[600px] overflow-y-auto min-w-0 rounded-2xl border border-line bg-surface p-3"
              aria-label="Danh sách node"
            >
              {!nodes.length && <p>Không có node phù hợp.</p>}
              {nodes.map((n) => (
                <button
                  type="button"
                  key={JSON.stringify([n.entity_type, n.entity_id])}
                  aria-pressed={node === n}
                  onClick={() =>
                    setSelected(JSON.stringify([n.entity_type, n.entity_id]))
                  }
                  className="block text-left w-full border-b border-line py-3 px-2 hover:bg-surface-2 focus-visible:outline break-words"
                >
                  <span className="block text-xs text-muted">
                    {n.entity_type}
                  </span>
                  <span className="text-sm">{n.entity_id}</span>
                </button>
              ))}
            </div>
            <section
              className="min-w-0 rounded-2xl border border-line bg-surface p-5"
              aria-label="Chi tiết node"
            >
              {node ? (
                <>
                  <h2 className="font-semibold break-words">
                    {node.entity_id}
                  </h2>
                  <dl className="text-sm mt-3">
                    {Object.entries(node.properties).map(([key, value]) => (
                      <div key={key} className="py-2 border-b border-line">
                        <dt className="font-medium">{key}</dt>
                        <dd className="whitespace-pre-wrap break-words mt-1">
                          {typeof value === "string"
                            ? value
                            : JSON.stringify(value)}
                        </dd>
                      </div>
                    ))}
                  </dl>
                  <h3 className="font-semibold mt-5">Nguồn đã xác minh</h3>
                  {node.sources.map((s) => (
                    <details
                      key={s.evidence_id}
                      className="mt-3 text-xs break-all"
                    >
                      <summary className="cursor-pointer">
                        {s.field} · Evidence {s.evidence_id}
                      </summary>
                      <p className="mt-2">SHA-256 nguồn: {s.source_sha256}</p>
                    </details>
                  ))}
                  <h3 className="font-semibold mt-5">
                    Quan hệ ({relations.length})
                  </h3>
                  {relations.map((e, i) => {
                    const other =
                      e.from[0] === node.entity_type &&
                      e.from[1] === node.entity_id
                        ? e.to
                        : e.from
                    return (
                      <div key={i} className="text-sm mt-3 break-words">
                        <p>
                          {e.from[1]} → {e.predicate} → {e.to[1]}
                        </p>
                        <button
                          type="button"
                          className="underline mt-1"
                          onClick={() => setSelected(JSON.stringify(other))}
                        >
                          Mở {other[1]}
                        </button>
                        {Object.keys(e.properties).length > 0 && (
                          <pre className="whitespace-pre-wrap break-words text-xs">
                            {JSON.stringify(e.properties, null, 2)}
                          </pre>
                        )}
                      </div>
                    )
                  })}
                  {!relations.length && (
                    <p className="mt-2 text-sm">
                      Không có cạnh nối node này trong SAMPLE.
                    </p>
                  )}
                </>
              ) : (
                <p className="text-sm text-muted">
                  Chọn node để đọc thuộc tính, nguồn và điều hướng cạnh thực.
                </p>
              )}
            </section>
          </div>
        </>
      )}
    </Page>
  )
}

export function BuilderControls() {
  const [status, setStatus] = useState<BuilderStatus>(),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [version, setVersion] = useState(0)
  function message(failure: unknown) {
    return failure instanceof ApiError && failure.status === 409
      ? "Trạng thái đã thay đổi hoặc thao tác chưa an toàn. Hãy tải lại trạng thái."
      : failure instanceof ApiError && failure.status === 503
        ? "Builder chưa khả dụng. Worker có thể chưa được cấu hình hoặc triển khai."
        : inspectionError(failure)
  }
  useEffect(() => {
    if (busy) return
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    async function refresh() {
      try {
        const value = await loadBuilderStatus(controller.signal)
        if (!controller.signal.aborted) {
          setStatus(value)
          setError("")
        }
      } catch (failure) {
        if (!controller.signal.aborted) {
          setStatus(undefined)
          setError(message(failure))
        }
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(refresh, 3000)
      }
    }
    refresh()
    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [version, busy])
  async function act(action: "build" | "stop" | "resume") {
    if (!status?.actions[action] || busy) return
    const runId =
      action === "build" ? `build-${crypto.randomUUID()}` : status.run_id
    if (!runId) return
    setBusy(true)
    setError("")
    try {
      setStatus(await runBuilderAction(action, runId))
    } catch (failure) {
      setStatus(undefined)
      setError(message(failure))
    } finally {
      setBusy(false)
      setVersion((value) => value + 1)
    }
  }
  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_420px] mb-5" aria-label="Điều khiển Builder"><Card title="Dựng đồ thị & vector · Builder thật"><div className="px-5 pb-5 text-sm space-y-3">
      <p className="text-xs text-muted">API thật · thao tác theo quyền Worker, không chạy pipeline mô phỏng.</p>
      {error && <p role="alert">{error}</p>}
      <p aria-live="polite">
        Trạng thái:{" "}
        {status
          ? builderStateLabel(status.state)
          : "Chưa đọc được trạng thái Worker"}
      </p>
      {status?.target && (
        <p className="break-words">
          Cấu hình đích: project {status.target.project_id} · database{" "}
          {status.target.database} · {status.target.namespace}
        </p>
      )}
      {status?.run_id && <p className="break-words">Run: {status.run_id}</p>}
      {status?.progress && (
        <p>
          Tiến độ bước {status.progress.stage}: {status.progress.done}/
          {status.progress.total}
        </p>
      )}
      {status?.progress && status.progress.total > 0 && (
        <Progress
          value={Math.min(
            100,
            (status.progress.done / status.progress.total) * 100,
          )}
        />
      )}
      {status?.error_code && (
        <p>
          {status.error_code === "LOCK_MOUNT"
            ? "Chưa xác minh được volume khóa dùng chung hoặc thiếu Docker inspection. Build bị chặn."
            : status.error_code === "INTERRUPTED" && status.state === "STOPPED"
              ? "Runner đã dừng tại checkpoint; chỉ Resume khi backend cho phép."
              : `Builder bị chặn: ${status.error_code}. Cần kiểm tra cấu hình, identity hoặc checkpoint.`}
        </p>
      )}
      <div className="flex flex-wrap gap-3">
        <Button
          disabled={busy || !status?.actions.build}
          onClick={() => act("build")}
        >
          Build
        </Button>
        <Button
          disabled={busy || !status?.actions.stop}
          onClick={() => act("stop")}
        >
          Stop
        </Button>
        <Button
          disabled={busy || !status?.actions.resume}
          onClick={() => act("resume")}
        >
          Resume
        </Button>
        <Button disabled aria-describedby="builder-delete-reason">
          Delete
        </Button>
        <Button
          disabled={busy}
          onClick={() => setVersion((value) => value + 1)}
        >
          Tải lại trạng thái
        </Button>
      </div>
      <p id="builder-delete-reason">
        Delete chưa có quyền xóa graph an toàn nên bị vô hiệu hóa. Production
        WRITE vẫn bị chặn.
      </p>
    </div></Card><Card title="Log tác vụ · Worker thật"><div className="px-5 pb-5"><Terminal lines={status ? [`Trạng thái: ${builderStateLabel(status.state)}`, `Run: ${status.run_id ?? "Chưa có"}`, ...(status.progress ? [`${status.progress.stage}: ${status.progress.done}/${status.progress.total}`] : ["Worker chưa cung cấp batch progress"]), ...(status.error_code ? [status.error_code] : []), "API hiện cung cấp status; chưa có stream log hoặc lịch sử job."] : [error || "Đang tải trạng thái Worker…"]} className="h-72" /></div></Card></div>
  )
}

export function Pipeline() {
  const data = useInspection(loadPipelineStatus),
    sample = useInspection(loadSampleInspection)
  return (
    <Page
      title="Pipeline & tác vụ"
      subtitle="Điều khiển Builder qua Worker nội bộ; runtime truy vấn và receipt SAMPLE hiển thị riêng."
      actions={
        <Button
          disabled={data.loading || sample.loading}
          onClick={() => {
            data.reload()
            sample.reload()
          }}
        >
          Kiểm tra lại
        </Button>
      }
    >
      <Notice {...data} retry={data.reload} />
      <Notice {...sample} retry={sample.reload} />
      {data.value && (
        <div className="grid sm:grid-cols-3 gap-4">
          {[
            ["Runtime truy vấn", data.value.phase.toUpperCase()],
            [
              "Request đang xử lý",
              data.value.active_requests ?? "Chưa xác minh",
            ],
            [
              "Query worker draining",
              data.value.draining === null
                ? "Chưa xác minh"
                : String(data.value.draining),
            ],
          ].map(([label, value]) => (
            <Card key={label} className="p-5">
              <p className="text-xs text-muted">{label}</p>
              <p className="font-semibold mt-3">{value}</p>
            </Card>
          ))}
        </div>
      )}
      <BuilderControls />
      {sample.value && (
        <section className="text-sm space-y-2 break-words">
          <h2 className="font-semibold">
            Receipt SAMPLE hoàn tất kiểm tra graph
          </h2>
          <p>Scope: SAMPLE · Stage: {sample.value.sample_receipt.stage}</p>
          <p>
            Đã xác minh {sample.value.counts.nodes} node,{" "}
            {sample.value.counts.edges} cạnh, {sample.value.counts.vectors}{" "}
            vector.
          </p>
          <p>Sealed: {sample.value.sample_receipt.sealed_at}</p>
          <p className="break-all">
            Receipt SHA-256: {sample.value.sample_receipt.receipt_sha256}
          </p>
          <p>
            Run ID / batch progress / thời gian build: UNSUPPORTED — receipt này
            không chứng minh các trường đó.
          </p>
        </section>
      )}
      <p className="mt-5 text-sm text-muted">
        Builder giữ policy và khóa của Runner; quyền ghi production chưa được
        cấp.
      </p>
    </Page>
  )
}

export function Benchmark() {
  const data = useInspection(loadSampleInspection),
    catalog = data.value?.datasets
  return (
    <Page
      title="Benchmark KAG"
      subtitle="Validation và độ phủ gold trên graph SAMPLE hiện tại. Metrics chỉ có sau evaluation hợp lệ."
      actions={
        <Button disabled={data.loading} onClick={data.reload}>
          Kiểm tra lại
        </Button>
      }
    >
      <Notice
        {...data}
        retry={data.reload}
        empty={catalog?.state === "AVAILABLE" && !catalog.datasets.length}
      />
      {catalog && (
        <>
          <p className="py-4">
            Catalog: {catalog.state} · Thực thi benchmark chính thức: BLOCKED
          </p>
          <p className="text-sm break-all">
            Graph fingerprint: {data.value?.graph_fingerprint}
          </p>
          <p className="text-sm break-all">
            Source catalog SHA-256: {data.value?.source_catalog_sha256}
          </p>
          <p className="text-sm">
            Model cấu hình:{" "}
            {data.value?.providers.configured_chat_model ?? "Chưa cấu hình"} ·
            Danh tính upstream: NOT VERIFIED
          </p>
          {catalog.datasets.map((row) => (
            <section
              key={row.id}
              className="my-5 p-5 rounded-2xl border border-line bg-surface text-sm space-y-2 break-words"
            >
              <h2 className="font-semibold">{row.id}</h2>
              {row.metadata && (
                <>
                  <p>
                    Dataset version: {row.metadata.dataset_version ?? "INVALID"}
                  </p>
                  <p>
                    Nhóm câu hỏi:{" "}
                    {Object.entries(row.metadata.category_counts)
                      .map(([category, count]) => `${category}: ${count}`)
                      .join(" · ") || "Chưa có schema hợp lệ"}
                  </p>
                  {row.metadata.generation_method && (
                    <p>
                      Phương pháp tạo: {row.metadata.generation_method} · Gold
                      cần human review
                    </p>
                  )}
                </>
              )}
              <p>
                Validation: {row.dataset_status ?? "INVALID"} ·{" "}
                {row.dataset_eligibility} ·{" "}
                {row.reason ?? "Có gold trong graph"}
              </p>
              <p>
                Tổng {row.record_count ?? "Chưa xác minh"} · Valid{" "}
                {row.record_count !== null && row.invalid_count !== null
                  ? row.record_count - row.invalid_count
                  : "Chưa xác minh"}{" "}
                · Invalid {row.invalid_count ?? "Chưa xác minh"} · Có gold{" "}
                {row.gold_count ?? "Chưa xác minh"}
              </p>
              <p>
                Eligible frozen {row.eligible_count} · Ineligible{" "}
                {row.ineligible_count} · Phạm vi: {row.eligibility_scope}; không
                chứng minh solver/effectivity.
              </p>
              <p className="break-all">
                Dataset SHA-256: {row.dataset_hash ?? "Chưa có dataset hợp lệ"}
              </p>
              {row.smoke && (
                <>
                  <p>
                    Review: {row.smoke.review_status} · Chưa có chứng nhận human
                    review · G1 eligible exploratory:{" "}
                    {row.smoke.g1_eligible_count}
                  </p>
                  <p>
                    Kết quả evaluation: {row.smoke.state} ·{" "}
                    {row.smoke.official_benchmark
                      ? "Dataset được chỉ định official trong frozen manifest; không chứng minh model correctness"
                      : "Không phải official benchmark"}
                  </p>
                  {row.smoke.state === "INVALID_RECEIPT" && (
                    <p role="alert">
                      Artifact không khớp dataset/graph/hash; metrics bị chặn.
                    </p>
                  )}
                  {Object.entries(row.smoke.runs).map(([mode, run]) => (
                    <div key={mode} className="space-y-1">
                      <h3 className="font-semibold">
                        {mode === "G1" ? "G1 Retrieval" : "G2 Solver"}:{" "}
                        {run?.status ?? "NOT_RUN"}
                      </h3>
                      {run ? (
                        <>
                          <p>
                            Requested {run.requested_count} · Attempted{" "}
                            {run.attempted_count} · Failed {run.failed_count} ·
                            Ineligible {run.ineligible_count}
                          </p>
                          <p>
                            {run.started_at} → {run.finished_at}
                          </p>
                          {run.configuration && (
                            <p>
                              Metric policy{" "}
                              {run.configuration.metric_policy_version} · Top k{" "}
                              {run.configuration.top_k} · Cutoffs{" "}
                              {run.configuration.ks.join(", ")} · Rank{" "}
                              {run.configuration.rank_semantics}
                            </p>
                          )}
                          {run.configuration?.metric_policy_version ===
                            "1.1" && (
                            <p>
                              source_span.* dùng rank trên toàn bộ items trả về;
                              document/unit/sign.* dùng rank theo channel.
                            </p>
                          )}
                          <p>
                            Latency mean (all attempted):{" "}
                            {run.latency_ms.all_attempted.mean?.toFixed(1) ??
                              "Chưa đo"}{" "}
                            ms
                          </p>
                          <details>
                            <summary className="cursor-pointer underline">
                              Metrics thực đo và mẫu số
                            </summary>
                            <dl>
                              {Object.entries(run.metrics).map(
                                ([name, metric]) => (
                                  <div key={name} className="py-1">
                                    <dt>{name}</dt>
                                    <dd>
                                      {metric.value ??
                                        "UNAVAILABLE / NOT_APPLICABLE"}{" "}
                                      · Scored {metric.scored_count}/
                                      {metric.eligible_count} · Failed{" "}
                                      {metric.failed_count} · Excluded{" "}
                                      {metric.excluded_count}
                                    </dd>
                                  </div>
                                ),
                              )}
                            </dl>
                          </details>
                        </>
                      ) : (
                        <p>
                          Chưa có execution artifact hợp lệ; metrics chưa đo.
                        </p>
                      )}
                    </div>
                  ))}
                </>
              )}
              <details>
                <summary className="cursor-pointer underline">
                  Gold thiếu trong SAMPLE
                </summary>
                {Object.entries(row.missing_gold).map(([kind, ids]) => (
                  <div key={kind} className="mt-2">
                    <p>
                      {kind}: {ids.length} ID
                    </p>
                    <ul className="ml-4 list-disc">
                      {ids.map((id) => (
                        <li key={id} className="break-words">
                          {id}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </details>
            </section>
          ))}
          <p className="mt-5 text-sm">
            SAMPLE smoke chỉ exploratory. Benchmark chính thức cần frozen
            manifest và review đủ điều kiện. Metrics null giữ nguyên; không suy
            thành PASS.
          </p>
        </>
      )}
    </Page>
  )
}
