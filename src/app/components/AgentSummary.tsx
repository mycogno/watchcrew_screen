import React from "react";

interface MotivationDetail {
  강도?: string;
  Graphic?: string;
  Orthographic?: string;
  Lexical?: string;
  Grammatical?: string;
  Examples?: string[];
}

interface AttachmentDetail {
  Value?: string;
  강도?: string;
  Graphic?: string;
  Orthographic?: string;
  Lexical?: string;
  Grammatical?: string;
  Examples?: string[];
}

interface AgentSummaryProps {
  동기?: Record<string, MotivationDetail | string>;
  애착?: Record<string, AttachmentDetail | string>;
  className?: string;
}

export function AgentSummary({
  동기,
  애착,
  className,
}: AgentSummaryProps) {
  // 동기 요약 추출
  const 동기요약 = 동기?.['동기 요약'] as string | undefined;
  
  // 애착 요약 추출
  const 애착요약 = 애착?.['애착 요약'] as string | undefined;
  
  const hasAny = !!(동기요약 || 애착요약);

  if (!hasAny) return null;

  return (
    <div className={className ?? "space-y-4"}>
      {동기요약 && (
        <div>
          <div className="font-semibold text-slate-700 mb-1">동기</div>
          <div className="ml-2 text-sm text-slate-600 whitespace-pre-wrap">{동기요약}</div>
        </div>
      )}
      {애착요약 && (
        <div>
          <div className="font-semibold text-slate-700 mb-1">애착</div>
          <div className="ml-2 text-sm text-slate-600 whitespace-pre-wrap">{애착요약}</div>
        </div>
      )}
    </div>
  );
}

export default AgentSummary;
