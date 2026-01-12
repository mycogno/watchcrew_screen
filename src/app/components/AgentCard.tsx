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
  prompt: string;
  team: string;
  createdAt: string;
  avatarSeed: string;
  teamName: string; // 실제 팀 이름
}

interface AgentCardProps {
  agent: Agent;
  onEdit: (id: string, name: string, prompt: string, team: string) => void;
  onDelete: (id: string) => void;
  homeTeamId?: string | null;
  awayTeamId?: string | null;
}

export function AgentCard({ agent, onEdit, onDelete, homeTeamId, awayTeamId }: AgentCardProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editName, setEditName] = useState(agent.name);
  const [editPrompt, setEditPrompt] = useState(agent.prompt);
  const [editTeam, setEditTeam] = useState<'home' | 'away'>(agent.team);

  const handleSave = () => {
    if (editName.trim() && editPrompt.trim()) {
      onEdit(agent.id, editName, editPrompt, editTeam);
      setIsEditing(false);
    }
  };

  const handleCancel = () => {
    setEditName(agent.name);
    setEditPrompt(agent.prompt);
    setEditTeam(agent.team);
    setIsEditing(false);
  };

  // DiceBear API를 사용한 아바타 URL
  const avatarUrl = `https://api.dicebear.com/7.x/avataaars/svg?seed=${agent.avatarSeed}`;

  const homeTeam = TEAMS.find(t => t.id === homeTeamId);
  const awayTeam = TEAMS.find(t => t.id === awayTeamId);
  const currentTeam = agent.team === 'home' ? homeTeam : awayTeam;

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
                <Button
                  type="button"
                  variant={editTeam === 'away' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setEditTeam('away')}
                  className="flex-1"
                  style={editTeam === 'away' ? { backgroundColor: awayTeam?.color, borderColor: awayTeam?.color } : {}}
                >
                  {awayTeam?.name || '어웨이팀'}
                </Button>
                <Button
                  type="button"
                  variant={editTeam === 'home' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setEditTeam('home')}
                  className="flex-1"
                  style={editTeam === 'home' ? { backgroundColor: homeTeam?.color, borderColor: homeTeam?.color } : {}}
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
                  variant={agent.team === 'home' ? 'default' : 'secondary'}
                  style={{ 
                    backgroundColor: currentTeam?.color || (agent.team === 'home' ? '#074CA1' : '#EA0029'),
                    borderColor: currentTeam?.color || (agent.team === 'home' ? '#074CA1' : '#EA0029'),
                    color: 'white'
                  }}
                >
                  {agent.teamName || currentTeam?.shortName || (agent.team === 'home' ? '홈팀' : '어웨이팀')}
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
          <p className="text-muted-foreground">{agent.prompt}</p>
        )}
      </CardContent>
    </Card>
  );
}