import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Button } from "./ui/button";
import { Textarea } from "./ui/textarea";
import { Label } from "./ui/label";
import { Sparkles } from "lucide-react";
import { TEAMS } from "./TeamSelection";
import { AgentSelectionModal } from "./AgentSelectionModal";

interface AgentCreatorProps {
  onCreateAgent: (
    name: string, 
    prompt: string,
    team: string,  // 팀 이름 (예: "samsung lions", "kia tigers")
    isHome: boolean,  // home인지 away인지
    avatarSeed?: string, 
    id?: string,
    createdAt?: string,
    dimensions?: Record<string, string>,
    채팅특성요약?: string,
    표현요약?: string
  ) => void;
  homeTeamId: string | null;
  awayTeamId: string | null;
}

export function AgentCreator({ onCreateAgent, homeTeamId, awayTeamId }: AgentCreatorProps) {
  const [prompt, setPrompt] = useState("");
  const [selectedTeamName, setSelectedTeamName] = useState<string>("");
  const [selectedIsHome, setSelectedIsHome] = useState<boolean>(true);
  const [showModal, setShowModal] = useState(false);

  const handleCreate = () => {
    if (prompt.trim() && selectedTeamName) {
      setShowModal(true);
    }
  };

  // 모달에서 선택한 에이전트 정보를 받아서 상위로 전달
  const handleSelectAgent = (
    name: string, 
    fullPrompt: string, 
    selectedTeam: string, 
    isHome: boolean,
    avatarSeed: string, 
    id?: string,
    createdAt?: string,
    dimensions?: Record<string, string>,
    채팅특성요약?: string,
    표현요약?: string
  ) => {
    // 상위 컴포넌트로 팀 이름과 isHome 전달
    onCreateAgent(name, fullPrompt, selectedTeam, isHome, avatarSeed, id, createdAt, dimensions, 채팅특성요약, 표현요약);
    
    setPrompt("");
    setSelectedTeamName("");
    setSelectedIsHome(true);
    setShowModal(false);
  };

  const homeTeam = TEAMS.find(t => t.id === homeTeamId);
  const awayTeam = TEAMS.find(t => t.id === awayTeamId);

  return (
    <Card className="border-2 border-primary/20">
      <CardHeader>
        <div className="flex items-center gap-2">
          <Sparkles className="size-6 text-primary" />
          <CardTitle>새 AI 팬 에이전트 생성</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label>에이전트가 응원하는 팀</Label>
          <div className="flex gap-2">
            <Button
              type="button"
              variant={selectedIsHome === false && selectedTeamName === awayTeam?.name ? 'default' : 'outline'}
              onClick={() => {
                setSelectedTeamName(awayTeam?.name || '');
                setSelectedIsHome(false);
              }}
              className="flex-1"
              style={selectedIsHome === false && selectedTeamName === awayTeam?.name ? { backgroundColor: awayTeam?.color, borderColor: awayTeam?.color } : {}}
            >
              {awayTeam?.name || '어웨이팀'}
            </Button>
            <Button
              type="button"
              variant={selectedIsHome === true && selectedTeamName === homeTeam?.name ? 'default' : 'outline'}
              onClick={() => {
                setSelectedTeamName(homeTeam?.name || '');
                setSelectedIsHome(true);
              }}
              className="flex-1"
              style={selectedIsHome === true && selectedTeamName === homeTeam?.name ? { backgroundColor: homeTeam?.color, borderColor: homeTeam?.color } : {}}
            >
              {homeTeam?.name || '홈팀'}
            </Button>
          </div>
        </div>
        <div className="space-y-2">
          <Label htmlFor="agent-prompt">에이전트 특징</Label>
          <Textarea
            id="agent-prompt"
            placeholder="예: 팀을 열렬히 응원하고 감정이 풍부한 팬. 득점할 때마다 환호하고 역전에 대한 희망을 놓지 않는 긍정적인 성격."
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={6}
            className="resize-none"
          />
        </div>
        <Button
          onClick={handleCreate}
          className="w-full"
          disabled={!prompt.trim() || !selectedTeamName}
        >
          <Sparkles className="size-4 mr-2" />
          에이전트 생성
        </Button>
      </CardContent>
      
      {/* 모달 연결 */}
      <AgentSelectionModal
        isOpen={showModal}
        onClose={() => setShowModal(false)}
        onSelectAgent={handleSelectAgent}
        team={selectedTeamName}
        isHome={selectedIsHome}
        prompt={prompt}
        homeTeamId={homeTeamId}
        awayTeamId={awayTeamId}
        contentClassName="max-w-5xl w-full max-h-[90vh] overflow-y-auto"
      />
    </Card>
  );
}