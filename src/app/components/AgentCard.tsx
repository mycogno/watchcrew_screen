import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Badge } from "./ui/badge";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogHeader,
  AlertDialogTitle,
} from "./ui/alert-dialog";
import AgentSummary from "./AgentSummary";
import { Pencil, Trash2, Check } from "lucide-react";
import { TEAMS } from "./TeamSelection";

export interface MotivationDetail {
  강도?: string;
  Graphic?: string;
  Orthographic?: string;
  Lexical?: string;
  Grammatical?: string;
  Examples?: string[];
}

export interface AttachmentDetail {
  Value?: string;
  강도?: string;
  Graphic?: string;
  Orthographic?: string;
  Lexical?: string;
  Grammatical?: string;
  Examples?: string[];
}

export interface Agent {
  id: string;
  name: string;
  userPrompt: string; // 사용자가 입력한 원본 프롬프트
  team: string; // 이제 팀 이름 (예: "samsung lions", "kia tigers")
  isHome: boolean; // home인지 away인지 구분
  createdAt: string;
  avatarSeed: string;
  동기?: Record<string, MotivationDetail | string>; // 7개 동기 항목 + 동기 요약
  애착?: Record<string, AttachmentDetail | string>; // 애착1, 애착2 등 + 애착 요약
}

interface AgentCardProps {
  agent: Agent;
  onEdit: (id: string, name: string, userPrompt: string, team: string, isHome: boolean) => void;
  onDelete: (id: string) => void;
  homeTeamId?: string | null;
  awayTeamId?: string | null;
  readOnly?: boolean;
}

export function AgentCard({ agent, onEdit, onDelete, homeTeamId, awayTeamId, readOnly }: AgentCardProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false);
  const [editName, setEditName] = useState(agent.name);

  const handleSave = () => {
    if (editName.trim()) {
      onEdit(agent.id, editName, agent.userPrompt, agent.team, agent.isHome);
      setIsEditing(false);
    }
  };

  const handleCancel = () => {
    setEditName(agent.name);
    setIsEditing(false);
  };

  // DiceBear API를 사용한 아바타 URL
  const avatarUrl = `https://api.dicebear.com/7.x/avataaars/svg?seed=${agent.avatarSeed}`;

  const homeTeam = TEAMS.find(t => t.id === homeTeamId);
  const awayTeam = TEAMS.find(t => t.id === awayTeamId);
  
  // 에이전트의 팀 이름으로 팀 데이터 찾기
  const agentTeamData = TEAMS.find(t => t.name.toLowerCase() === agent.team.toLowerCase() || t.shortName.toLowerCase() === agent.team.toLowerCase());
  const agentTeamColor = agentTeamData?.color || '#999';
  const agentTeamShortName = agentTeamData?.shortName || agent.team;

  return (
    <Card className="hover:shadow-lg transition-all group">
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          {isEditing ? (
            <div className="flex-1 flex items-center gap-2">
              <img 
                src={avatarUrl} 
                alt={agent.name} 
                className="size-10 rounded-full bg-slate-100 flex-shrink-0"
              />
              <Input
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                placeholder="에이전트 이름"
                className="flex-1"
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleSave();
                  if (e.key === 'Escape') handleCancel();
                }}
              />
              <div className="flex gap-1 flex-shrink-0">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleSave}
                  className="hover:bg-green-100"
                >
                  <Check className="size-4 text-green-600" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleCancel}
                  className="hover:bg-red-100"
                >
                  ✕
                </Button>
              </div>
            </div>
          ) : (
            <>
              <img 
                src={avatarUrl} 
                alt={agent.name} 
                className="size-10 rounded-full bg-slate-100 flex-shrink-0"
              />
              <div className="flex items-center gap-2 flex-1 flex-wrap">
                <CardTitle>{agent.name}</CardTitle>
                <div className="flex items-center gap-1">
                  <Badge 
                    variant={agent.isHome ? 'default' : 'secondary'}
                    style={{ 
                      backgroundColor: agentTeamColor,
                      borderColor: agentTeamColor,
                      color: 'white'
                    }}
                  >
                    {agentTeamShortName}
                  </Badge>
                  {!readOnly && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        e.preventDefault();
                        setIsEditing(true);
                      }}
                      className="opacity-0 group-hover:opacity-100 transition-opacity"
                    >
                      <Pencil className="size-4" />
                    </Button>
                  )}
                </div>
              </div>
            </>
          )}
          {!isEditing && !readOnly && (
            <div className="flex gap-2 flex-shrink-0">
              <Button
                variant="ghost"
                size="sm"
                onClick={(e) => {
                  e.stopPropagation();
                  e.preventDefault();
                  setIsConfirmingDelete(true);
                }}
              >
                <Trash2 className="size-4 text-destructive" />
              </Button>
            </div>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <AgentSummary
          동기={agent.동기}
          애착={agent.애착}
        />
      </CardContent>

      <AlertDialog open={isConfirmingDelete} onOpenChange={setIsConfirmingDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>에이전트 삭제</AlertDialogTitle>
            <AlertDialogDescription>
              &quot;{agent.name}&quot;을(를) 정말 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="flex justify-end gap-2">
            <AlertDialogCancel>취소</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                onDelete(agent.id);
                setIsConfirmingDelete(false);
              }}
              className="bg-destructive hover:bg-destructive/90 text-white"
            >
              삭제
            </AlertDialogAction>
          </div>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}