import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Button } from "./ui/button";
import { Textarea } from "./ui/textarea";
import { Label } from "./ui/label";
import { Sparkles } from "lucide-react";
import { TEAMS } from "./TeamSelection";
import { AgentSelectionModal } from "./AgentSelectionModal";

interface AgentCreatorProps {
  // [수정됨] dimensions?: Record<string, string> 추가
  // 상위 컴포넌트(WatchGame)로 데이터를 넘겨주는 함수 정의
  onCreateAgent: (
    name: string, 
    prompt: string, 
    team: 'home' | 'away', 
    avatarSeed?: string, 
    teamName?: string,
    id?: string,
    createdAt?: string,
    dimensions?: Record<string, string> 
  ) => void;
  homeTeamId: string | null;
  awayTeamId: string | null;
}

export function AgentCreator({ onCreateAgent, homeTeamId, awayTeamId }: AgentCreatorProps) {
  const [prompt, setPrompt] = useState("");
  const [team, setTeam] = useState<'home' | 'away'>('home');
  // [수정됨] 에러가 발생했던 줄입니다. 깨끗하게 다시 작성했습니다.
  const [showModal, setShowModal] = useState(false);

  const handleCreate = () => {
    if (prompt.trim()) {
      setShowModal(true);
    }
  };

  // [수정됨] 모달에서 선택한 에이전트 정보(dimensions 포함)를 받아서 상위로 전달
  const handleSelectAgent = (
    name: string, 
    fullPrompt: string, 
    selectedTeam: string, // 모달에서 string으로 옴
    avatarSeed: string, 
    teamName: string,
    id?: string,
    createdAt?: string,
    dimensions?: Record<string, string> // ✅ 추가됨
  ) => {
    // team 타입 변환 (string -> 'home' | 'away')
    const finalTeam = selectedTeam === 'home' || selectedTeam === 'away' ? selectedTeam : 'home';
    
    // 상위 컴포넌트로 dimensions까지 포함해서 전달
    onCreateAgent(name, fullPrompt, finalTeam, avatarSeed, teamName, id, createdAt, dimensions);
    
    setPrompt("");
    setTeam('home');
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
              variant={team === 'away' ? 'default' : 'outline'}
              onClick={() => setTeam('away')}
              className="flex-1"
              style={team === 'away' ? { backgroundColor: awayTeam?.color, borderColor: awayTeam?.color } : {}}
            >
              {awayTeam?.name || '어웨이팀'}
            </Button>
            <Button
              type="button"
              variant={team === 'home' ? 'default' : 'outline'}
              onClick={() => setTeam('home')}
              className="flex-1"
              style={team === 'home' ? { backgroundColor: homeTeam?.color, borderColor: homeTeam?.color } : {}}
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
          disabled={!prompt.trim()}
        >
          <Sparkles className="size-4 mr-2" />
          에이전트 생성
        </Button>
      </CardContent>
      
      {/* 모달 연결 */}
      <AgentSelectionModal
        isOpen={showModal}
        onClose={() => setShowModal(false)}
        onSelectAgent={handleSelectAgent} // 위에서 수정한 핸들러 연결
        team={team}
        prompt={prompt}
        homeTeamId={homeTeamId}
        awayTeamId={awayTeamId}
        // 이전에 모달 크기 문제 해결할 때 썼던 className 유지 또는 제거 (Modal 내부에서 style로 처리했으므로 여기선 제거해도 무방)
        contentClassName="max-w-5xl w-full max-h-[90vh] overflow-y-auto"
      />
    </Card>
  );
}