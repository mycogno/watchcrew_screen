import React from "react";

interface AgentSummaryProps {
  동기요약?: string;
  애착요약?: string;
  채팅내용설명?: string;
  채팅표현설명?: string;
  className?: string;
}

export function AgentSummary({
  동기요약,
  애착요약,
  채팅내용설명,
  채팅표현설명,
  className,
}: AgentSummaryProps) {
  const hasAny = !!(동기요약 || 애착요약 || 채팅내용설명 || 채팅표현설명);

  if (!hasAny) return null;

  return (
    <div className={className ?? "space-y-4"}>
      {동기요약 && (
        <div>
          <div className="font-semibold text-slate-700 mb-1">동기</div>
          <div className="ml-2 text-sm text-slate-600">{동기요약}</div>
        </div>
      )}
      {애착요약 && (
        <div>
          <div className="font-semibold text-slate-700 mb-1">애착</div>
          <div className="ml-2 text-sm text-slate-600">{애착요약}</div>
        </div>
      )}
      {채팅내용설명 && (
        <div>
          <div className="font-semibold text-slate-700 mb-1">내용</div>
          <div className="ml-2 text-sm text-slate-600">{채팅내용설명}</div>
        </div>
      )}
      {채팅표현설명 && (
        <div>
          <div className="font-semibold text-slate-700 mb-1">표현</div>
          <div className="ml-2 text-sm text-slate-600">{채팅표현설명}</div>
        </div>
      )}
    </div>
  );
}

export default AgentSummary;
