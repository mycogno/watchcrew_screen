import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { Card, CardContent } from "./ui/card";
import { Check } from "lucide-react";
import { Badge } from "./ui/badge";
import { TEAMS } from "./TeamSelection";
import { API_URL } from "../../config/api";

interface AgentCandidate {
  id: string;
  name: string;
  team: string;
  userPrompt: string;
  팬의특성: Record<string, string>;
  애착: Record<string, string>;
  채팅특성: Record<string, string>;
  표현: Record<string, string>;
  채팅특성요약?: string;
  표현요약?: string;
}

interface AgentSelectionModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectAgent: (
    name: string,
    userPrompt: string,
    team: string,
    isHome: boolean,
    avatarSeed: string,
    id?: string,
    createdAt?: string,
    팬의특성?: Record<string, string>,
    애착?: Record<string, string>,
    채팅특성?: Record<string, string>,
    표현?: Record<string, string>,
    채팅특성요약?: string,
    표현요약?: string
  ) => void;
  team: string; // 팀 이름
  isHome: boolean; // home인지 away인지
  prompt: string;
  homeTeamId: string | null;
  awayTeamId: string | null;
  contentClassName?: string;
}

export function AgentSelectionModal({
  isOpen,
  onClose,
  onSelectAgent,
  team,
  isHome,
  prompt,
  homeTeamId,
  awayTeamId,
  contentClassName,
}: AgentSelectionModalProps) {
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [candidates, setCandidates] = useState<AgentCandidate[]>([]);
  const [loading, setLoading] = useState(false);
  const abortControllerRef = useState<AbortController | null>(null)[0];

  const fetchCandidates = async (signal?: AbortSignal) => {
  setLoading(true);
  try {
    const res = await fetch(`${API_URL}/generate_candidates`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt, team }),
        signal,
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`Request failed ${res.status}: ${text}`);
      }
      const data: AgentCandidate[] = await res.json();
      setCandidates(data);
    } catch (err: any) {
      if (err.name === 'AbortError') {
        // 요청이 취소됨
        return;
      }
      console.error("generate_candidates fetch failed:", err);
      setCandidates([]);
    } finally {
      setLoading(false);
    }
  };

  // When modal opens, fetch candidates and show loading skeleton
  useEffect(() => {
    let controller: AbortController | null = null;
    if (isOpen) {
      setSelectedIds([]);
      setCandidates([]);
      controller = new AbortController();
      // @ts-ignore
      abortControllerRef && (abortControllerRef.current = controller);
      fetchCandidates(controller.signal);
    } else {
      // 모달 닫힐 때 요청 취소
      if (abortControllerRef && abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      setCandidates([]);
      setSelectedIds([]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    return () => {
      if (controller) controller.abort();
    };
  }, [isOpen]);

  const homeTeam = TEAMS.find(t => t.id === homeTeamId);
  const awayTeam = TEAMS.find(t => t.id === awayTeamId);
  const currentTeamObj = TEAMS.find(t => t.name === team);
  const realTeamName = currentTeamObj?.name || team;

  const handleToggleSelect = (id: string) => {
    setSelectedIds(prev => 
      prev.includes(id) 
        ? prev.filter(selectedId => selectedId !== id)
        : [...prev, id]
    );
  };

  const handleConfirm = () => {
    const selectedCandidates = candidates.filter(c => selectedIds.includes(c.id));
    selectedCandidates.forEach(candidate => {
      const agentData = {
        id: `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`,
        name: candidate.name,
        userPrompt: candidate.userPrompt,
        team: candidate.team,
        isHome: isHome,
        createdAt: new Date().toISOString(),
        avatarSeed: candidate.id,
        팬의특성: candidate.팬의특성,
        애착: candidate.애착,
        채팅특성: candidate.채팅특성,
        표현: candidate.표현,
        채팅특성요약: candidate.채팅특성요약,
        표현요약: candidate.표현요약,
      };
      console.log('Registering Agent:', agentData);
      if (typeof onSelectAgent === 'function') {
        onSelectAgent(
          agentData.name,
          agentData.userPrompt,
          agentData.team,
          agentData.isHome,
          agentData.avatarSeed,
          agentData.id,
          agentData.createdAt,
          agentData.팬의특성,
          agentData.애착,
          agentData.채팅특성,
          agentData.표현,
          agentData.채팅특성요약,
          agentData.표현요약
        );
      }
    });
    setSelectedIds([]);
  };

  const handleClose = () => {
    setSelectedIds([]);
    setCandidates([]);
    onClose();
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent 
      className={contentClassName ?? "max-w-[90vw] w-full sm:max-w-[90vw] max-h-[95vh] overflow-y-auto !max-w-[90vw]"}
      style={{ 
      maxWidth: '95vw', // 화면 너비의 95% (강제 적용)
      width: 'fit-content'     // 가능한 꽉 채우기
    }}
      >
        <DialogHeader>
          <DialogTitle className="text-xl">에이전트 페르소나 선택</DialogTitle>
          {/* 팀 태그 표시 */}
          <div className="flex items-center gap-2 mt-2">
            <span className="text-sm text-muted-foreground">선택한 팀:</span>
            <span
              className="inline-block px-3 py-1 rounded-full text-xs font-semibold"
              style={{
                backgroundColor: currentTeamObj?.color || '#0ea5e9',
                color: 'white',
                border: `1px solid ${currentTeamObj?.color || '#0ea5e9'}`,
              }}
            >
              {realTeamName}
            </span>
          </div>
          <p className="text-sm text-muted-foreground mt-2">
            입력하신 특징을 기반으로 생성된 에이전트 후보입니다. 마음에 드는 페르소나를 선택하세요. (다중 선택 가능)
          </p>
        </DialogHeader>

        <div className="py-4">
          {/* <div className="grid grid-cols-1 sm:grid-cols-2 gap-4"> */}
          {/* <div className="grid grid-cols-1 gap-4"> */}
          <div className="flex gap-4 overflow-x-auto pb-4">
            {loading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <Card key={`skel-${i}`} className="animate-pulse border-2 border-slate-200 h-60 min-w-[320px] flex-shrink-0">
                  <CardContent className="p-3 h-full">
                    <div className="space-y-2">
                      <div className="h-4 bg-slate-200 rounded w-1/3 mb-2" />
                      <div className="h-3 bg-slate-200 rounded w-full" />
                    </div>
                  </CardContent>
                </Card>
              ))
            ) : (
              candidates.map((candidate) => {
                const isSelected = selectedIds.includes(candidate.id);
                const avatarUrl = `https://api.dicebear.com/7.x/avataaars/svg?seed=${encodeURIComponent(candidate.id)}`;
                return (
                  <Card
                    key={candidate.id}
                    className={`cursor-pointer transition-all hover:shadow-lg border-2 h-80 w-[320px] flex-shrink-0 ${
                      isSelected
                        ? 'border-primary ring-2 ring-primary ring-offset-2'
                        : 'border-slate-200 hover:border-primary/50'
                    }`}
                    onClick={() => handleToggleSelect(candidate.id)}
                  >
                    <CardContent className="p-3 h-full flex flex-col justify-between">
                      <div className="space-y-2">
                        <div className="flex items-center gap-4">
                          <div className="flex-shrink-0">
                            {isSelected ? (
                              <div className="bg-primary text-white rounded-full p-1.5">
                                <Check className="size-4" />
                              </div>
                            ) : (
                              <div className="border-2 border-slate-300 rounded-full p-1.5 size-7" />
                            )}
                          </div>

                          <img
                            src={avatarUrl}
                            alt={candidate.name}
                            className="size-10 rounded-full bg-slate-100 flex-shrink-0"
                          />
                          <div className="flex items-center gap-2 flex-1 flex-wrap">
                            <h3 className="font-bold text-base">{candidate.name}</h3>
                          </div>
                        </div>

                        <div className="pl-4 space-y-1">
                          {candidate.팬의특성 && Object.keys(candidate.팬의특성).length > 0 && (
                            <div className="text-sm">
                              <div className="font-semibold text-slate-700 mb-0.5">팬의특성</div>
                              <div className="ml-2 space-y-0.5">
                                {Object.entries(candidate.팬의특성).map(([subKey, subValue]) => (
                                  <div key={subKey} className="text-xs">
                                    <span className="text-slate-600">{subKey}:</span>
                                    <span className="text-slate-500 ml-1">{String(subValue)}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                          {candidate.애착 && Object.keys(candidate.애착).length > 0 && (
                            <div className="text-sm">
                              <div className="font-semibold text-slate-700 mb-0.5">애착</div>
                              <div className="ml-2 space-y-0.5">
                                {Object.entries(candidate.애착).map(([subKey, subValue]) => (
                                  <div key={subKey} className="text-xs">
                                    <span className="text-slate-600">{subKey}:</span>
                                    <span className="text-slate-500 ml-1">{String(subValue)}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                          {candidate.채팅특성요약 && (
                            <div className="text-sm">
                              <div className="font-semibold text-slate-700 mb-0.5">채팅 특성</div>
                              <div className="ml-2 text-xs text-slate-600">{candidate.채팅특성요약}</div>
                            </div>
                          )}
                          {candidate.표현요약 && (
                            <div className="text-sm">
                              <div className="font-semibold text-slate-700 mb-0.5">표현</div>
                              <div className="ml-2 text-xs text-slate-600">{candidate.표현요약}</div>
                            </div>
                          )}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                );
              })
            )}
          </div>
        </div>

        <DialogFooter>
          <div className="flex items-center justify-between w-full">
            <span className="text-sm text-muted-foreground">
              {selectedIds.length > 0 && `${selectedIds.length}개 선택됨`}
            </span>
            <div className="flex gap-2">
              <Button variant="outline" onClick={handleClose}>
                취소
              </Button>
              <Button onClick={handleConfirm} disabled={selectedIds.length === 0}>
                선택 완료 ({selectedIds.length})
              </Button>
            </div>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}