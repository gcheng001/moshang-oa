import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  CircleAlert,
  ShieldAlert,
  XCircle,
} from "lucide-react";
import { api, ApiError } from "../api";
import type { ApprovalReview } from "../types";
import { Dialog, money, Spinner } from "../components/ui";

export function ApprovalDetail() {
  const { id } = useParams();
  const lawcaseId = Number(id);
  const navigate = useNavigate();

  const [review, setReview] = useState<ApprovalReview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [conflictReviewed, setConflictReviewed] = useState(false);
  const [conflictMemo, setConflictMemo] = useState("");
  const [riskReviewed, setRiskReviewed] = useState(false);
  const [riskMemo, setRiskMemo] = useState("");

  const [dialog, setDialog] = useState<"approve" | "reject" | null>(null);
  const [memo, setMemo] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string[]>([]);
  const [done, setDone] = useState<string>("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setReview(await api.approvalCheck(lawcaseId));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [lawcaseId]);

  useEffect(() => {
    void load();
  }, [load]);

  const conflictFindings = review?.conflict.findings ?? [];
  const duplicateFindings = review?.duplicate_filing.findings ?? [];
  const isRisk = review ? review.risk_charge.result !== "not_applicable" : false;

  const hardBlockers = review
    ? [
        ...review.completeness.missing.map((m) => `资料不完整: ${m}`),
        ...review.conflict.blockers,
        ...review.duplicate_filing.blockers,
        ...(review.fee_explanation?.blockers ?? []),
      ]
    : [];

  const approveReady =
    hardBlockers.length === 0 &&
    (conflictFindings.length === 0 || (conflictReviewed && conflictMemo.trim() !== "")) &&
    (!isRisk || riskReviewed);

  // 依据预检结果代拟驳回理由，供合伙人直接采纳或修改
  const buildRejectDraft = (): string => {
    if (!review) return "";
    const items: string[] = [];
    review.completeness.missing.forEach((m) => items.push(`立案资料不完整，缺少「${m}」，请补齐后重新提交`));
    review.conflict.blockers.forEach((b) => items.push(b));
    if (review.conflict.blockers.length === 0) {
      conflictFindings.forEach((f) =>
        items.push(
          `利益冲突线索未排除：「${f.matched_name}」在案件 ${f.case_no || f.case_id} 中为${f.relation}，请先完成利冲审查并出具结论`,
        ),
      );
    }
    review.duplicate_filing.blockers.forEach((b) => items.push(b));
    if (review.duplicate_filing.blockers.length === 0) {
      duplicateFindings.forEach((f) =>
        items.push(
          `与案件 ${f.case_no || f.case_id} 存在当事人/案由重叠（${[...f.principal_overlap, ...f.opponent_overlap].join("、")}），请说明是否重复立案或关联案件`,
        ),
      );
    }
    (review.fee_explanation?.blockers ?? []).forEach((b) => items.push(b));
    if (isRisk && review.risk_charge.verdict === "issues_found") {
      (review.risk_charge.issues ?? []).forEach((i) => items.push(i));
    }
    if (items.length === 0) return "";
    const body = items.map((s, i) => `${i + 1}、${s}`).join("；\n");
    return `经审查，本案暂不符合立案条件，予以驳回，请按以下意见补正后重新提交审批：\n${body}。`;
  };

  const submit = async (action: "approve" | "reject") => {
    setSubmitting(true);
    setSubmitError([]);
    try {
      const result =
        action === "approve"
          ? await api.approve(lawcaseId, {
              memo,
              conflict_reviewed: conflictReviewed,
              conflict_memo: conflictMemo,
              risk_reviewed: riskReviewed,
              risk_memo: riskMemo,
            })
          : await api.reject(lawcaseId, memo);
      setDialog(null);
      setDone(
        action === "approve"
          ? `已通过：${result.case_no} 现为「${result.new_status_name}」`
          : `已驳回：${result.case_no} 现为「${result.new_status_name}」`,
      );
      window.dispatchEvent(new Event("moshang:pending-refresh"));
    } catch (err) {
      if (err instanceof ApiError && err.gateErrors) setSubmitError(err.gateErrors);
      else setSubmitError([err instanceof Error ? err.message : String(err)]);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="p-6">
        <BackButton onClick={() => navigate("/approvals")} />
        <Spinner label="正在执行审批前检查（完整性 / 利冲 / 重复立案 / 风险收费）…" />
      </div>
    );
  }

  if (error || !review) {
    return (
      <div className="p-6">
        <BackButton onClick={() => navigate("/approvals")} />
        <div className="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          检查失败：{error || "未知错误"}
        </div>
      </div>
    );
  }

  const detail = review.detail as Record<string, unknown>;

  return (
    <div className="flex h-full flex-col">
      <header className="border-b border-zinc-200 bg-white px-6 py-4">
        <BackButton onClick={() => navigate("/approvals")} />
        <div className="mt-2 flex items-baseline gap-3">
          <h2 className="text-base font-semibold">{review.case_no || `案件 #${review.lawcase_id}`}</h2>
          <span className="text-xs text-zinc-400">
            {String(detail.baseTypeName ?? "")} · {String(detail.causeAction ?? "")}
          </span>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto p-6">
        {done ? (
          <div className="mx-auto max-w-xl rounded-xl border border-emerald-200 bg-emerald-50 p-6 text-center">
            <CheckCircle2 className="mx-auto mb-2 h-8 w-8 text-emerald-500" />
            <p className="text-sm font-medium text-emerald-800">{done}</p>
            <p className="mt-1 text-xs text-emerald-600">已回读 OA 校验状态变更</p>
            <button
              onClick={() => navigate("/approvals")}
              className="mt-4 rounded-lg bg-emerald-600 px-4 py-1.5 text-sm text-white hover:bg-emerald-700"
            >
              返回待审清单
            </button>
          </div>
        ) : (
          <div className="mx-auto max-w-3xl space-y-4">
            <section className="rounded-xl border border-zinc-200 bg-white p-5">
              <h3 className="mb-3 text-sm font-semibold text-zinc-800">案件信息</h3>
              <div className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm">
                <Field label="委托人" value={review.conflict.principals.join("、")} />
                <Field label="对方当事人" value={review.conflict.opponents.join("、")} />
                <Field label="经办律师" value={String(detail.empNames ?? "")} />
                <Field label="收费方式" value={String(detail.chargeMethodName ?? "")} />
                <Field label="委托费用" value={money(detail.chargeAmount as number | null)} />
                <Field label="受理日期" value={String(detail.shouliDate ?? "").slice(0, 10)} />
              </div>
              {Boolean(detail.caseSummary) && (
                <p className="mt-3 rounded-lg bg-zinc-50 p-3 text-xs leading-relaxed text-zinc-600">
                  {String(detail.caseSummary)}
                </p>
              )}
            </section>

            <CheckCard
              title="资料完整性"
              ok={review.completeness.result === "complete"}
              okText="必填资料齐全"
              problems={review.completeness.missing.map((m) => `缺少：${m}`)}
              warning={
                review.completeness.result === "complete" && review.completeness.warnings.length > 0
                  ? review.completeness.warnings.join("；")
                  : undefined
              }
            />

            <CheckCard
              title="利冲检索"
              ok={review.conflict.result === "no_exact_adverse_match"}
              okText="未发现对立方向的利冲命中"
              problems={review.conflict.blockers}
              warning={
                conflictFindings.length > 0
                  ? `发现 ${conflictFindings.length} 条利冲线索，须合伙人人工复核`
                  : undefined
              }
            >
              {conflictFindings.length > 0 && (
                <>
                  <FindingTable
                    rows={conflictFindings.map((f) => ({
                      key: `${f.case_id}-${f.matched_name}`,
                      no: f.case_no || String(f.case_id),
                      name: f.matched_name,
                      relation: f.relation,
                      status: f.status_name || "",
                      severity: f.severity,
                    }))}
                  />
                  <div className="mt-3 space-y-2 rounded-lg bg-amber-50 p-3">
                    <label className="flex items-center gap-2 text-xs font-medium text-amber-800">
                      <input
                        type="checkbox"
                        checked={conflictReviewed}
                        onChange={(e) => setConflictReviewed(e.target.checked)}
                        className="h-3.5 w-3.5 accent-amber-600"
                      />
                      我已逐条人工复核上述利冲线索，确认不构成利益冲突或已依规处理
                    </label>
                    <input
                      value={conflictMemo}
                      onChange={(e) => setConflictMemo(e.target.value)}
                      placeholder="复核结论（必填，将写入审批意见）"
                      className="w-full rounded-md border border-amber-200 bg-white px-2.5 py-1.5 text-xs outline-none focus:border-amber-400"
                    />
                  </div>
                </>
              )}
            </CheckCard>

            <CheckCard
              title="重复立案检查"
              ok={review.duplicate_filing.result === "no_duplicate_filing_match"}
              okText="未发现 OA 内重复立案"
              problems={review.duplicate_filing.blockers}
              warning={
                duplicateFindings.length > 0 && review.duplicate_filing.blockers.length === 0
                  ? `发现 ${duplicateFindings.length} 条当事人/案由重叠案件，请确认是否关联案件`
                  : undefined
              }
            >
              {duplicateFindings.length > 0 && (
                <FindingTable
                  rows={duplicateFindings.map((f) => ({
                    key: String(f.case_id),
                    no: f.case_no || String(f.case_id),
                    name: [...f.principal_overlap, ...f.opponent_overlap].join("、"),
                    relation: f.relation,
                    status: f.status_name || "",
                    severity: f.severity,
                  }))}
                />
              )}
            </CheckCard>

            {review.fee_explanation && review.fee_explanation.result !== "not_applicable" && (
              <CheckCard
                title="低收费审查（< ¥5,000）"
                ok={review.fee_explanation.result === "ok"}
                okText={`委托收费 ${money(review.fee_explanation.amount)}，已填写收费说明`}
                problems={review.fee_explanation.blockers ?? []}
              >
                {review.fee_explanation.memo && (
                  <blockquote className="mt-2 rounded-lg border-l-2 border-zinc-300 bg-zinc-50 p-3 text-xs leading-relaxed text-zinc-600">
                    {review.fee_explanation.memo}
                  </blockquote>
                )}
              </CheckCard>
            )}

            {isRisk && (
              <CheckCard
                title="风险代理收费审查"
                ok={false}
                okText=""
                problems={[]}
                warning="本案为风险代理收费。以下为系统初步判断，供参考，是否通过由合伙人最终决定。"
              >
                <div className="mt-3 space-y-3">
                  <div>
                    <div className="mb-1 text-xs font-medium text-zinc-500">收费方案（OA 收费说明）</div>
                    {review.risk_charge.scheme ? (
                      <blockquote className="rounded-lg border-l-2 border-indigo-300 bg-indigo-50/50 p-3 text-sm leading-relaxed text-zinc-800">
                        {review.risk_charge.scheme}
                      </blockquote>
                    ) : (
                      <div className="rounded-lg bg-red-50 p-3 text-xs text-red-600">
                        OA 未填写收费方案，无法审查收费结构
                      </div>
                    )}
                  </div>

                  <div className="grid grid-cols-3 gap-3 text-xs">
                    <Field label="标的额" value={money(review.risk_charge.subject_amount)} />
                    <Field label="OA 登记收费" value={money(review.risk_charge.registered_fee)} />
                    <Field label="分段收费上限" value={money(review.risk_charge.graduated_cap)} />
                  </div>

                  {(review.risk_charge.cap_breakdown?.length ?? 0) > 0 && (
                    <div className="overflow-hidden rounded-lg border border-zinc-200">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="bg-zinc-50 text-left text-zinc-500">
                            <th className="px-3 py-1.5 font-medium">标的区间</th>
                            <th className="px-3 py-1.5 font-medium">费率</th>
                            <th className="px-3 py-1.5 text-right font-medium">本段金额</th>
                            <th className="px-3 py-1.5 text-right font-medium">本段上限</th>
                          </tr>
                        </thead>
                        <tbody>
                          {review.risk_charge.cap_breakdown!.map((t) => (
                            <tr key={t.range} className="border-t border-zinc-100 text-zinc-600">
                              <td className="px-3 py-1.5">{t.range}</td>
                              <td className="px-3 py-1.5">{t.rate}</td>
                              <td className="px-3 py-1.5 text-right">{money(t.portion)}</td>
                              <td className="px-3 py-1.5 text-right">{money(t.fee)}</td>
                            </tr>
                          ))}
                          <tr className="border-t border-zinc-200 bg-zinc-50 font-medium text-zinc-800">
                            <td className="px-3 py-1.5" colSpan={3}>
                              合计上限（司发通〔2021〕87号）
                            </td>
                            <td className="px-3 py-1.5 text-right">{money(review.risk_charge.graduated_cap)}</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  )}

                  <div
                    className={`rounded-lg p-3 text-xs ${
                      review.risk_charge.verdict === "preliminary_pass"
                        ? "bg-emerald-50 text-emerald-800"
                        : "bg-red-50 text-red-700"
                    }`}
                  >
                    <p className="mb-1 font-semibold">
                      初步判断：
                      {review.risk_charge.verdict === "preliminary_pass" ? "初步符合规定" : "发现不符合项"}
                    </p>
                    {(review.risk_charge.issues?.length ?? 0) > 0 && (
                      <ul className="list-inside list-disc space-y-0.5">
                        {review.risk_charge.issues!.map((i) => (
                          <li key={i}>{i}</li>
                        ))}
                      </ul>
                    )}
                    {(review.risk_charge.suggestions?.length ?? 0) > 0 && (
                      <ul className="mt-1.5 space-y-0.5">
                        {review.risk_charge.suggestions!.map((s) => (
                          <li key={s}>建议：{s}</li>
                        ))}
                      </ul>
                    )}
                  </div>

                  {(review.risk_charge.notes?.length ?? 0) > 0 && (
                    <ul className="space-y-0.5 text-[11px] text-zinc-400">
                      {review.risk_charge.notes!.map((n) => (
                        <li key={n}>· {n}</li>
                      ))}
                    </ul>
                  )}

                  <div className="space-y-2 rounded-lg bg-amber-50 p-3">
                    <label className="flex items-start gap-2 text-xs font-medium text-amber-800">
                      <input
                        type="checkbox"
                        checked={riskReviewed}
                        onChange={(e) => setRiskReviewed(e.target.checked)}
                        className="mt-0.5 h-3.5 w-3.5 accent-amber-600"
                      />
                      我已审阅收费方案与系统初步判断，作为合伙人确认本案风险代理收费可以通过（含书面合同与告知义务已履行）
                    </label>
                    <input
                      value={riskMemo}
                      onChange={(e) => setRiskMemo(e.target.value)}
                      placeholder="风险收费复核意见（选填，将写入审批意见）"
                      className="w-full rounded-md border border-amber-200 bg-white px-2.5 py-1.5 text-xs outline-none focus:border-amber-400"
                    />
                  </div>
                </div>
              </CheckCard>
            )}

            {hardBlockers.length > 0 && (
              <div className="flex items-start gap-2.5 rounded-xl border border-red-200 bg-red-50 p-4">
                <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-red-500" />
                <div className="text-sm text-red-700">
                  <p className="mb-1 font-medium">存在阻断项，无法通过审批（可驳回）：</p>
                  <ul className="list-inside list-disc space-y-0.5 text-xs">
                    {hardBlockers.map((b) => (
                      <li key={b}>{b}</li>
                    ))}
                  </ul>
                </div>
              </div>
            )}

            {submitError.length > 0 && (
              <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
                <p className="mb-1 font-medium">提交失败：</p>
                <ul className="list-inside list-disc space-y-0.5 text-xs">
                  {submitError.map((e) => (
                    <li key={e}>{e}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>

      {!done && (
        <footer className="flex items-center justify-end gap-3 border-t border-zinc-200 bg-white px-6 py-3.5">
          <button
            onClick={() => {
              setMemo(buildRejectDraft());
              setDialog("reject");
            }}
            className="rounded-lg border border-red-200 px-5 py-2 text-sm font-medium text-red-600 hover:bg-red-50"
          >
            驳回
          </button>
          <button
            disabled={!approveReady}
            onClick={() => {
              setMemo("");
              setDialog("approve");
            }}
            title={approveReady ? "" : "存在阻断项或未完成人工确认"}
            className="rounded-lg bg-indigo-600 px-5 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            通过审批
          </button>
        </footer>
      )}

      <Dialog
        open={dialog === "approve"}
        title={`确认通过 ${review.case_no || `#${review.lawcase_id}`}？`}
        onClose={() => setDialog(null)}
      >
        <p className="mb-3 text-sm text-zinc-500">通过后案件状态将变为「办理中」，此操作写入 OA。</p>
        <textarea
          value={memo}
          onChange={(e) => setMemo(e.target.value)}
          placeholder="审批意见（可选）"
          rows={3}
          className="mb-4 w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm outline-none focus:border-indigo-500"
        />
        <DialogActions
          confirmText={submitting ? "提交中…" : "确认通过"}
          confirmClass="bg-indigo-600 hover:bg-indigo-700"
          disabled={submitting}
          onCancel={() => setDialog(null)}
          onConfirm={() => void submit("approve")}
        />
      </Dialog>

      <Dialog
        open={dialog === "reject"}
        title={`驳回 ${review.case_no || `#${review.lawcase_id}`}`}
        onClose={() => setDialog(null)}
      >
        <p className="mb-3 text-sm text-zinc-500">
          驳回后案件状态将变为「立案未通过」，审批意见必填。
          {memo.trim() !== "" && (
            <span className="mt-1 block text-xs text-indigo-600">
              已按预检发现的问题代拟驳回理由，可直接提交或修改后提交。
            </span>
          )}
        </p>
        <textarea
          value={memo}
          onChange={(e) => setMemo(e.target.value)}
          placeholder="驳回理由（必填，将反馈给经办律师）"
          rows={memo.split("\n").length > 3 ? 8 : 4}
          autoFocus
          className="mb-4 w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm leading-relaxed outline-none focus:border-red-400"
        />
        <DialogActions
          confirmText={submitting ? "提交中…" : "确认驳回"}
          confirmClass="bg-red-600 hover:bg-red-700"
          disabled={submitting || !memo.trim()}
          onCancel={() => setDialog(null)}
          onConfirm={() => void submit("reject")}
        />
      </Dialog>
    </div>
  );
}

function DialogActions({
  confirmText,
  confirmClass,
  disabled,
  onCancel,
  onConfirm,
}: {
  confirmText: string;
  confirmClass: string;
  disabled: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="flex justify-end gap-2">
      <button
        onClick={onCancel}
        className="rounded-lg border border-zinc-300 px-4 py-1.5 text-sm text-zinc-600 hover:bg-zinc-50"
      >
        取消
      </button>
      <button
        onClick={onConfirm}
        disabled={disabled}
        className={`rounded-lg px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50 ${confirmClass}`}
      >
        {confirmText}
      </button>
    </div>
  );
}

function BackButton({ onClick }: { onClick: () => void }) {
  return (
    <button onClick={onClick} className="flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-600">
      <ArrowLeft className="h-3.5 w-3.5" />
      返回待审清单
    </button>
  );
}

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <span className="text-xs text-zinc-400">{label}</span>
      <div className="text-sm text-zinc-800">{value || "—"}</div>
    </div>
  );
}

function CheckCard({
  title,
  ok,
  okText,
  problems,
  warning,
  children,
}: {
  title: string;
  ok: boolean;
  okText: string;
  problems: string[];
  warning?: string;
  children?: React.ReactNode;
}) {
  const hasProblem = problems.length > 0;
  const icon = hasProblem ? (
    <XCircle className="h-4.5 w-4.5 text-red-500" />
  ) : ok ? (
    <CheckCircle2 className="h-4.5 w-4.5 text-emerald-500" />
  ) : warning ? (
    <AlertTriangle className="h-4.5 w-4.5 text-amber-500" />
  ) : (
    <CircleAlert className="h-4.5 w-4.5 text-zinc-400" />
  );

  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-5">
      <div className="mb-2 flex items-center gap-2">
        {icon}
        <h3 className="text-sm font-semibold text-zinc-800">{title}</h3>
      </div>
      {hasProblem ? (
        <ul className="list-inside list-disc space-y-0.5 text-xs text-red-600">
          {problems.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      ) : warning ? (
        <p className="text-xs text-amber-700">{warning}</p>
      ) : (
        <p className="text-xs text-zinc-400">{okText}</p>
      )}
      {children}
    </section>
  );
}

function FindingTable({
  rows,
}: {
  rows: { key: string; no: string; name: string; relation: string; status: string; severity: string }[];
}) {
  return (
    <div className="mt-3 overflow-hidden rounded-lg border border-zinc-200">
      <table className="w-full text-xs">
        <thead>
          <tr className="bg-zinc-50 text-left text-zinc-500">
            <th className="px-3 py-2 font-medium">案号</th>
            <th className="px-3 py-2 font-medium">命中主体</th>
            <th className="px-3 py-2 font-medium">关系</th>
            <th className="px-3 py-2 font-medium">状态</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key} className="border-t border-zinc-100">
              <td className="px-3 py-2 font-medium text-zinc-800">{r.no}</td>
              <td className="px-3 py-2 text-zinc-700">{r.name}</td>
              <td className="px-3 py-2 text-zinc-600">{r.relation}</td>
              <td className="px-3 py-2">
                <span
                  className={`rounded-full px-1.5 py-0.5 ${
                    r.severity === "high" || r.severity === "block"
                      ? "bg-red-50 text-red-600"
                      : "bg-amber-50 text-amber-700"
                  }`}
                >
                  {r.status || r.severity}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
