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

interface AgentCandidate {
  id: string;
  name: string;
  dimensions: Record<string, string>;
  fullPrompt: string;
  team: string;
}

interface AgentSelectionModalProps {
  isOpen: boolean;
  onClose: () => void;
  // now includes avatarSeed to apply selected candidate's avatar to created agent
  onSelectAgent: (name: string, prompt: string, team: string, avatarSeed: string, teamName: string) => void;
  team: string;
  prompt: string;
  homeTeamId: string | null;
  awayTeamId: string | null;
  // optional className applied to DialogContent to control modal size
  contentClassName?: string;
}

export function AgentSelectionModal({
  isOpen,
  onClose,
  onSelectAgent,
  team,
  prompt,
  homeTeamId,
  awayTeamId,
  contentClassName,
}: AgentSelectionModalProps) {
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [candidates, setCandidates] = useState<AgentCandidate[]>([]);
  const [loading, setLoading] = useState(false);
  const abortControllerRef = useState<AbortController | null>(null)[0];

  const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

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
  const currentTeamObj = team === 'home' 
    ? homeTeam 
    : (team === 'away' ? awayTeam : TEAMS.find(t => t.id === team));
  const realTeamName = currentTeamObj?.name || (team === 'home' ? '홈팀' : '어웨이팀');

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
      // Create Agent object according to interface Agent
      const agentData = {
        id: `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`,
        name: candidate.name,
        prompt: candidate.fullPrompt,
        team: candidate.team,
        createdAt: new Date().toISOString(),
        avatarSeed: candidate.id,
        teamName: realTeamName
      };
      console.log('Registering Agent:', agentData);
      // Pass all fields to onSelectAgent if possible, otherwise update downstream to accept agentData
      if (typeof onSelectAgent === 'function') {
        // If onSelectAgent expects full agent object, pass agentData
        // Otherwise, pass individual fields
        onSelectAgent(
          agentData.name,
          agentData.prompt,
          agentData.team,
          agentData.avatarSeed,
          agentData.teamName,
          agentData.id,
          agentData.createdAt
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
      <DialogContent className={contentClassName ?? "max-w-[2000px] w-[98vw] max-h-[95vh] overflow-y-auto"}>
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
                    className={`cursor-pointer transition-all hover:shadow-lg border-2 h-60 min-w-[320px] flex-shrink-0 ${
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

                        <div className="pl-11 space-y-1">
                          {Object.entries(candidate.dimensions).map(([key, value]) => (
                            <div key={key} className="text-sm">
                              <span className="font-semibold text-slate-700">{key}:</span>
                              <span className="text-slate-600 ml-1">{value}</span>
                            </div>
                          ))}
                        </div>

                        <div className="pl-11">
                          <p className="text-sm text-muted-foreground">{candidate.fullPrompt}</p>
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