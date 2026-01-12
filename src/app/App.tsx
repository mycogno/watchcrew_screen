import { useState, useEffect } from "react";
import { AgentCreator } from "./components/AgentCreator";
import { AgentCard, Agent } from "./components/AgentCard";
import { WatchGame } from "./components/WatchGame";
import { TeamSelection, TEAMS } from "./components/TeamSelection";
import { Button } from "./components/ui/button";
import { Users, Play, ArrowLeft } from "lucide-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "./components/ui/alert-dialog";

// 로컬스토리지 키
const STORAGE_KEY = "ai-fan-agents";

// 10개 팀별 에이전트 템플릿
const TEAM_AGENT_TEMPLATES: Record<string, { name: string; prompt: string; avatarSeed: string }> = {
  samsung: {
    name: "삼성 라이온즈 팬",
    prompt: "오랜 기간 삼성라이온즈를 응원해온 팬임. 팀이 잘 할 때는 잘 호응하지만, 팀이 못할때는 꽤 비판적이고 까칠한 말투를 가지고 있음.",
    avatarSeed: "samsung-fan-001",
  },
  kia: {
    name: "KIA 타이거즈 팬",
    prompt: "이우성 선수의 팬임. 이우성 선수는 KIA 타이거즈의 선수임. 매우 희망적이고 부드러운 말투를 가지고 있음.",
    avatarSeed: "kia-fan-002",
  },
  lg: {
    name: "LG 트윈스 팬",
    prompt: "LG 트윈스의 열정적인 팬으로 잠실 야구장의 분위기를 사랑함. 공격적이고 적극적인 응원 스타일을 가지고 있음.",
    avatarSeed: "lg-fan-003",
  },
  doosan: {
    name: "두산 베어스 팬",
    prompt: "두산 베어스의 오랜 팬으로 전통과 역사를 중요시함. 차분하지만 강한 신념을 가진 말투를 사용함.",
    avatarSeed: "doosan-fan-004",
  },
  ssg: {
    name: "SSG 랜더스 팬",
    prompt: "SSG 랜더스의 신생팀 팬으로 새로운 도전을 응원함. 밝고 긍정적이며 신선한 에너지를 가지고 있음.",
    avatarSeed: "ssg-fan-005",
  },
  kt: {
    name: "kt wiz 팬",
    prompt: "kt wiz의 젊은 팬으로 데이터와 전략을 중요시함. 분석적이고 논리적인 응원 스타일을 가지고 있음.",
    avatarSeed: "kt-fan-006",
  },
  nc: {
    name: "NC 다이노스 팬",
    prompt: "NC 다이노스의 열혈 팬으로 창단 이후 꾸준히 응원해옴. 끈기있고 묵묵한 응원 스타일을 가지고 있음.",
    avatarSeed: "nc-fan-007",
  },
  hanwha: {
    name: "한화 이글스 팬",
    prompt: "한화 이글스의 오랜 팬으로 힘든 시기를 함께 버텨옴. 유머러스하면서도 진심 어린 응원을 보냄.",
    avatarSeed: "hanwha-fan-008",
  },
  lotte: {
    name: "롯데 자이언츠 팬",
    prompt: "롯데 자이언츠의 부산 팬으로 지역 사랑이 강함. 열정적이고 시끌벅적한 응원 문화를 사랑함.",
    avatarSeed: "lotte-fan-009",
  },
  kiwoom: {
    name: "키움 히어로즈 팬",
    prompt: "키움 히어로즈의 젊은 팬으로 팀의 성장을 함께 지켜봄. 감성적이고 따뜻한 말투를 가지고 있음.",
    avatarSeed: "kiwoom-fan-010",
  },
};

function App() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [currentScreen, setCurrentScreen] = useState<'team-selection' | 'setup' | 'watch'>('team-selection');
  const [homeTeamId, setHomeTeamId] = useState<string | null>(null);
  const [awayTeamId, setAwayTeamId] = useState<string | null>(null);
  const [userTeam, setUserTeam] = useState<string | null>(null);
  const [showResetDialog, setShowResetDialog] = useState(false);

  // Load agents from localStorage on mount
  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      try {
        setAgents(JSON.parse(stored));
      } catch (error) {
        console.error("Failed to load agents:", error);
      }
    }
  }, []);

  // Save agents to localStorage whenever they change
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(agents));
  }, [agents]);

  const handleCreateAgent = (name: string, prompt: string, team: string, avatarSeed?: string, teamName?: string) => {
    // team: 'home' | 'away' or team id
    let realTeamName = teamName;
    let teamId = team;
    if (!teamName && (team === 'home' || team === 'away')) {
      // If home/away, get id from homeTeamId/awayTeamId
      teamId = team === 'home' ? homeTeamId : awayTeamId;
      realTeamName = TEAMS.find(t => t.id === teamId)?.name || '';
    } else if (!teamName) {
      realTeamName = TEAMS.find(t => t.id === team)?.name || '';
    }
    const newAgent: Agent = {
      id: `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`,
      name,
      prompt,
      team,
      createdAt: new Date().toISOString(),
      avatarSeed: avatarSeed ? avatarSeed : Math.random().toString(36).substring(7),
      teamName: realTeamName || '',
    };
    setAgents((prev) => [newAgent, ...prev]);
  };

  const handleEditAgent = (id: string, name: string, prompt: string, team: string) => {
    setAgents((prev) =>
      prev.map((agent) =>
        agent.id === id ? { ...agent, name, prompt, team } : agent
      )
    );
  };

  const handleDeleteAgent = (id: string) => {
    setAgents((prev) => prev.filter((agent) => agent.id !== id));
  };

  const handleComplete = () => {
    setCurrentScreen('watch');
  };

  const handleBackToSetup = () => {
    setCurrentScreen('setup');
  };

  const handleBackToTeamSelection = () => {
    // 에이전트가 있으면 확인 다이얼로그 표시
    if (agents.length > 0) {
      setShowResetDialog(true);
    } else {
      // 에이전트가 없으면 바로 팀 선택으로 이동
      proceedToTeamSelection();
    }
  };

  const proceedToTeamSelection = () => {
    setAgents([]);
    setCurrentScreen('team-selection');
    setHomeTeamId(null);
    setAwayTeamId(null);
    setUserTeam(null);
    setShowResetDialog(false);
  };

  const handleLoadTestAgents = () => {
    // homeTeamId와 awayTeamId가 없으면 에이전트를 생성하지 않음
    if (!homeTeamId || !awayTeamId) {
      return;
    }

    const newTestAgents: Agent[] = [];
    const timestamp = Date.now();

    // 홈팀 에이전트 생성
    const homeTemplate = TEAM_AGENT_TEMPLATES[homeTeamId];
    if (homeTemplate) {
      newTestAgents.push({
        id: `home-${homeTeamId}-${timestamp}`,
        name: homeTemplate.name,
        prompt: homeTemplate.prompt,
        team: homeTeamId,
        createdAt: new Date().toISOString(),
        avatarSeed: homeTemplate.avatarSeed,
        teamName: TEAMS.find(t => t.id === homeTeamId)?.name || '',
      });
    }

    // 어웨이팀 에이전트 생성
    const awayTemplate = TEAM_AGENT_TEMPLATES[awayTeamId];
    if (awayTemplate) {
      newTestAgents.push({
        id: `away-${awayTeamId}-${timestamp}`,
        name: awayTemplate.name,
        prompt: awayTemplate.prompt,
        team: awayTeamId,
        createdAt: new Date().toISOString(),
        avatarSeed: awayTemplate.avatarSeed,
        teamName: TEAMS.find(t => t.id === awayTeamId)?.name || '',
      });
    }
    
    setAgents((prev) => [...newTestAgents, ...prev]);
  };

  // Show Watch Game Screen
  if (currentScreen === 'watch') {
    return <WatchGame selectedAgents={agents} onBack={handleBackToSetup} userTeam={userTeam} homeTeamId={homeTeamId} awayTeamId={awayTeamId} />;
  }

  // Show Setup Screen
  if (currentScreen === 'setup') {
    return (
      <>
        <AlertDialog open={showResetDialog} onOpenChange={setShowResetDialog}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>에이전트 초기화 확인</AlertDialogTitle>
              <AlertDialogDescription>
                기존 에이전트가 모두 초기화됩니다. 계속하시겠습니까?
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>취소</AlertDialogCancel>
              <AlertDialogAction onClick={proceedToTeamSelection}>
                계속
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 p-6">
          <div className="max-w-6xl mx-auto space-y-8">
            {/* Back Button */}
            <div>
              <Button variant="outline" onClick={handleBackToTeamSelection}>
                <ArrowLeft className="size-4 mr-2" />
                경기 팀 설정
              </Button>
            </div>

            {/* Header */}
            <header className="text-center space-y-2">
              <div className="flex items-center justify-center gap-3">
                <Users className="size-10 text-primary" />
                <h1 className="text-primary">AI 팬 에이전트 설정</h1>
              </div>
              <p className="text-muted-foreground">
                경기를 함께 즐길 나만의 AI 팬을 만들어보세요
              </p>
            </header>

            {/* Agent Creator */}
            <AgentCreator onCreateAgent={handleCreateAgent} homeTeamId={homeTeamId} awayTeamId={awayTeamId} />

            {/* Agents List */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h2>내 에이전트 목록</h2>
                <span className="text-muted-foreground">
                  {agents.length}개의 에이전트
                </span>
              </div>

              {agents.length === 0 ? (
                <div className="text-center py-12 bg-white rounded-lg border-2 border-dashed">
                  <Users className="size-12 mx-auto text-muted-foreground/50 mb-4" />
                  <p className="text-muted-foreground">
                    아직 생성된 에이전트가 없습니다.
                    <br />
                    위에서 새로운 AI 팬 에이전트를 만들어보세요!
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4" key={`agent-list-${agents.length}`}>
                  {agents.map((agent) => (
                    <AgentCard
                      key={agent.id}
                      agent={agent}
                      onEdit={handleEditAgent}
                      onDelete={handleDeleteAgent}
                      homeTeamId={homeTeamId}
                      awayTeamId={awayTeamId}
                    />
                  ))}
                </div>
              )}
            </div>

            {/* Info Message or Complete Button */}
            {agents.length > 0 && agents.length < 2 && (
              <div className="sticky bottom-6 bg-amber-50 rounded-lg border-2 border-amber-200 p-4 shadow-lg">
                <div className="flex items-center gap-3">
                  <Users className="size-5 text-amber-600" />
                  <span className="text-amber-800">
                    최소 <strong>2개 이상</strong>의 에이전트가 있어야 다음 단계로 진행할 수 있습니다.
                  </span>
                </div>
              </div>
            )}

            {/* Complete Button */}
            {agents.length >= 2 && userTeam && (
              <div className="sticky bottom-6 bg-white/90 backdrop-blur-sm rounded-lg border-2 border-primary/20 p-4 shadow-lg">
                <div className="flex items-center justify-between gap-4">
                  <div className="flex items-center gap-2">
                    <Users className="size-5 text-primary" />
                    <span>
                      <strong>{agents.length}개</strong>의 에이전트가 준비되었습니다
                    </span>
                  </div>
                  <Button
                    size="lg"
                    onClick={handleComplete}
                  >
                    <Play className="size-4 mr-2" />
                    설정 완료
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>
      </>
    );
  }

  // Show Team Selection Screen
  return <TeamSelection onSelectTeams={(homeId, awayId, userTeam) => {
    setHomeTeamId(homeId);
    setAwayTeamId(awayId);
    setUserTeam(userTeam);
    setCurrentScreen('setup');
  }} />;
}

export default App;