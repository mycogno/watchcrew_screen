import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Button } from "./ui/button";
import { Textarea } from "./ui/textarea";
import { Input } from "./ui/input";
import { Badge } from "./ui/badge";
import { Pencil, Trash2, Users, Check } from "lucide-react";
import { TEAMS } from "./TeamSelection";

export interface Agent {
  id: string;
  name: string;
  userPrompt: string; // 사용자가 입력한 원본 프롬프트
  team: string; // 이제 팀 이름 (예: "samsung lions", "kia tigers")
  isHome: boolean; // home인지 away인지 구분
  createdAt: string;
  avatarSeed: string;
  동기?: Record<string, { example_value: string; explanation: string }>; // 스포츠 시청 동기, 채팅 참여 동기
  동기요약?: string; // 동기 요약 설명
  애착?: Record<string, { example_value: string; explanation: string }>; // 애착의 대상, 애착의 강도/단계
  애착요약?: string; // 애착 요약 설명
  내용?: Record<string, { example_value: string; explanation: string }>; // Attribution of Responsibility 등
  채팅내용설명?: string; // 채팅 내용 요약 설명
  표현?: Record<string, { example_value: string; explanation: string }>; // Tone and Linguistic Style 등
  채팅표현설명?: string; // 채팅 표현 요약 설명
}

interface AgentCardProps {
  agent: Agent;
  onEdit: (id: string, name: string, userPrompt: string, team: string, isHome: boolean) => void;
  onDelete: (id: string) => void;
  homeTeamId?: string | null;
  awayTeamId?: string | null;
}

export function AgentCard({ agent, onEdit, onDelete, homeTeamId, awayTeamId }: AgentCardProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editName, setEditName] = useState(agent.name);
  const [editPrompt, setEditPrompt] = useState(agent.userPrompt);
  const [editTeam, setEditTeam] = useState<string>(agent.team);
  const [editIsHome, setEditIsHome] = useState<boolean>(agent.isHome);

  const handleSave = () => {
    if (editName.trim() && editPrompt.trim()) {
      onEdit(agent.id, editName, editPrompt, editTeam, editIsHome);
      setIsEditing(false);
    }
  };

  const handleCancel = () => {
    setEditName(agent.name);
    setEditPrompt(agent.userPrompt);
    setEditTeam(agent.team);
    setEditIsHome(agent.isHome);
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
    <Card className="hover:shadow-lg transition-all">
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          {isEditing ? (
            <div className="flex-1 space-y-2">
              <Input
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                placeholder="에이전트 이름"
              />
              <div className="flex gap-2">
                {/* 팀 이름 선택 */}
                <Button
                  type="button"
                  variant={editTeam === awayTeam?.name ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => {
                    setEditTeam(awayTeam?.name || 'away');
                    setEditIsHome(false);
                  }}
                  className="flex-1"
                  style={editTeam === awayTeam?.name ? { backgroundColor: awayTeam?.color, borderColor: awayTeam?.color } : {}}
                >
                  {awayTeam?.name || '어웨이팀'}
                </Button>
                <Button
                  type="button"
                  variant={editTeam === homeTeam?.name ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => {
                    setEditTeam(homeTeam?.name || 'home');
                    setEditIsHome(true);
                  }}
                  className="flex-1"
                  style={editTeam === homeTeam?.name ? { backgroundColor: homeTeam?.color, borderColor: homeTeam?.color } : {}}
                >
                  {homeTeam?.name || '홈팀'}
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
              </div>
            </>
          )}
          {!isEditing && (
            <div className="flex gap-2 flex-shrink-0">
              <Button
                variant="ghost"
                size="sm"
                onClick={(e) => {
                  e.stopPropagation();
                  e.preventDefault();
                  setIsEditing(true);
                }}
              >
                <Pencil className="size-4" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={(e) => {
                  e.stopPropagation();
                  e.preventDefault();
                  onDelete(agent.id);
                }}
              >
                <Trash2 className="size-4 text-destructive" />
              </Button>
            </div>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {isEditing ? (
          <>
            <Textarea
              value={editPrompt}
              onChange={(e) => setEditPrompt(e.target.value)}
              placeholder="에이전트 특징을 설명해주세요"
              rows={4}
              className="resize-none"
            />
            <div className="flex gap-2 justify-end">
              <Button variant="outline" size="sm" onClick={handleCancel}>
                취소
              </Button>
              <Button size="sm" onClick={handleSave}>
                저장
              </Button>
            </div>
          </>
        ) : (
          <>
            {/* 동기, 애착, 내용(채팅내용설명), 표현(채팅표현설명) 표시 */}
            {(agent.동기요약 || agent.애착요약 || agent.채팅내용설명 || agent.채팅표현설명) && (
              <div className="space-y-2">
                {agent.동기요약 && (
                  <div>
                    <div className="font-semibold text-slate-700 mb-1">동기</div>
                    <div className="ml-2 text-sm text-slate-600">{agent.동기요약}</div>
                  </div>
                )}
                {agent.동기요약 && (agent.애착요약 || agent.채팅내용설명 || agent.채팅표현설명) && (
                  <div className="border-t border-slate-200" />
                )}
                {agent.애착요약 && (
                  <div>
                    <div className="font-semibold text-slate-700 mb-1">애착</div>
                    <div className="ml-2 text-sm text-slate-600">{agent.애착요약}</div>
                  </div>
                )}
                {agent.애착요약 && (agent.채팅내용설명 || agent.채팅표현설명) && (
                  <div className="border-t border-slate-200" />
                )}
                {agent.채팅내용설명 && (
                  <div>
                    <div className="font-semibold text-slate-700 mb-1">내용</div>
                    <div className="ml-2 text-sm text-slate-600">{agent.채팅내용설명}</div>
                  </div>
                )}
                {agent.채팅내용설명 && agent.채팅표현설명 && (
                  <div className="border-t border-slate-200" />
                )}
                {agent.채팅표현설명 && (
                  <div>
                    <div className="font-semibold text-slate-700 mb-1">표현</div>
                    <div className="ml-2 text-sm text-slate-600">{agent.채팅표현설명}</div>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}