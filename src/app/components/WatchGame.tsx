import { useState, useEffect, useRef } from "react";
import { Agent, AgentCard } from "./AgentCard";
import { Button } from "./ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "./ui/card";
import { Input } from "./ui/input";
import { Badge } from "./ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "./ui/dialog";
import {
  ArrowLeft,
  Send,
  Video,
  Users,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { TEAMS } from "./TeamSelection";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "./ui/tabs";
import { playHistoryData } from "../data/playHistory";
import { API_URL } from "../../config/api";

interface WatchGameProps {
  selectedAgents: Agent[];
  onBack: () => void;
  userTeam: string | null;
  homeTeamId: string | null;
  awayTeamId: string | null;
}

interface ChatMessage {
  id: string;
  agentId: string;
  agentName: string;
  team: string; // canonical team id (예: "samsung", "kia")
  isHome: boolean; // home인지 away인지
  message: string;
  timestamp: string;
  avatarSeed?: string;
  isTyping?: boolean; // 타이핑 중 상태를 표시하기 위한 플래그
}

interface PlayData {
  inning: number;
  batterAppearanceOrder: number;
  seqNo: number;
  offensiveTeam: string;
  defensiveTeam: string;
  seqDescription: string;
  pitcherName: string;
  batterName: string;
  lineupSlot: number;
  strike: number;
  ball: number;
  out: number;
  ballCount: string;
  pitchResult: string;
  pitchType: string;
  pitchSpeed: number;
  totalPitches: number;
  pitchTime: string;
  runnerOnFirst: number;
  runnerOnSecond: number;
  runnerOnThird: number;
  plateAppearance: number;
  atBat: number;
  hit: number;
  run: number;
  runBattedIn: number;
  homeRun: number;
  baseOnBalls: number;
  struckOut: number;
  seqType: number;
  homeTeam: string;
  awayTeam: string;
  homeScore: number;
  awayScore: number;
  homeHit: number;
  awayHit: number;
  homeWalks: number;
  awayWalks: number;
  homeError: number;
  awayError: number;
}

export function WatchGame({
  selectedAgents,
  onBack,
  userTeam,
  homeTeamId,
  awayTeamId,
}: WatchGameProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputMessage, setInputMessage] = useState("");
  const [showAgentInfo, setShowAgentInfo] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false); // 메시지 생성 중 상태
  const [contextMemory, setContextMemory] = useState<Array<{speaker: string, text: string}>>([]); // context_memory for orchestrator
  const [expandedBatters, setExpandedBatters] = useState<
    Set<number>
  >(new Set()); // 확장된 타자 목록 (batterAppearanceOrder 기준) - 초기값 비움
  const shouldAutoScrollRef = useRef(true); // 자동 스크롤 여부 (useRef 사용)
  const chatRef = useRef<HTMLDivElement>(null);

  // 예시 문자 중계 데이터 (여러 개)
  const [playHistory, setPlayHistory] =
    useState<PlayData[]>(playHistoryData);

  // 이닝  초/말별로 데이터 그룹화
  const groupedByInningAndHalf = playHistory.reduce(
    (acc, play) => {
      const inning = play.inning;
      // 홈팀 공격이면 "말", 어웨이팀 공격이면 "초"
      const half =
        play.offensiveTeam === play.homeTeam ? "말" : "초";
      const key = `${inning}-${half}`;

      if (!acc[key]) {
        acc[key] = [];
      }
      acc[key].push(play);
      return acc;
    },
    {} as Record<string, PlayData[]>,
  );

  // 이닝별로 데이터 그룹화 (탭 표시용)
  const groupedByInning = playHistory.reduce(
    (acc, play) => {
      const inning = play.inning;
      if (!acc[inning]) {
        acc[inning] = [];
      }
      acc[inning].push(play);
      return acc;
    },
    {} as Record<number, PlayData[]>,
  );

  // 존재하는 이닝 목록 (정렬)
  const existingInnings = Object.keys(groupedByInning)
    .map(Number)
    .sort((a, b) => a - b);

  // 가장 최근 이닝 (기본 선택)
  const latestInning =
    existingInnings.length > 0
      ? Math.max(...existingInnings).toString()
      : "1";

  const [selectedInning, setSelectedInning] =
    useState<string>(latestInning);

  // selectedInning이 변경되어야 할 때 업데이트
  useEffect(() => {
    if (existingInnings.length > 0) {
      const latest = Math.max(...existingInnings).toString();
      setSelectedInning(latest);
    }
  }, [playHistory]);

  const homeTeam = TEAMS.find((t) => t.id === homeTeamId);
  const awayTeam = TEAMS.find((t) => t.id === awayTeamId);

  // 타자별로 플레이 데이터 그룹화
  const groupedByBatter = playHistory.reduce(
    (acc, play) => {
      const key = play.batterAppearanceOrder;
      if (!acc[key]) {
        acc[key] = [];
      }
      acc[key].push(play);
      return acc;
    },
    {} as Record<number, PlayData[]>,
  );

  // batterAppearanceOrder 기준 내림차순 정렬 (최신 타자가 먼저)
  const sortedBatterKeys = Object.keys(groupedByBatter)
    .map(Number)
    .sort((a, b) => b - a);

  // 타자 토글 함수
  const toggleBatter = (batterOrder: number) => {
    setExpandedBatters((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(batterOrder)) {
        newSet.delete(batterOrder);
      } else {
        newSet.add(batterOrder);
      }
      return newSet;
    });
  };

  // 이벤트 타입 및 구 번호 추출 함수
  const getEventInfo = (
    description: string,
    pitchResult: string,
  ) => {
    // 구 번호 추출 (예: "2구 볼" -> 2)
    const pitchNumMatch = description.match(/(\d+)구/);
    const pitchNumber = pitchNumMatch ? pitchNumMatch[1] : null;

    // 이벤트 타입 결정
    let eventType:
      | "strike"
      | "ball"
      | "hit"
      | "foul"
      | "result" = "result";
    let eventColor = "bg-slate-500"; // 기본값
    let eventLabel = "";

    if (description.includes("번트파울")) {
      eventType = "foul";
      eventColor = "bg-yellow-500";
      eventLabel = "번트파울";
    } else if (description.includes("파울")) {
      eventType = "foul";
      eventColor = "bg-yellow-500";
      eventLabel = "파울";
    } else if (description.includes("스트라이크")) {
      eventType = "strike";
      eventColor = "bg-yellow-500";
      eventLabel = "스트라이크";
    } else if (description.includes("헛스윙")) {
      eventType = "strike";
      eventColor = "bg-yellow-500";
      eventLabel = "헛스윙";
    } else if (description.includes("볼")) {
      eventType = "ball";
      eventColor = "bg-green-500";
      eventLabel = "볼";
    } else if (description.includes("타격")) {
      eventType = "hit";
      eventColor = "bg-blue-500";
      eventLabel = "타격";
    } else if (pitchResult === "F") {
      eventType = "foul";
      eventColor = "bg-yellow-500";
      eventLabel = "파울";
    } else if (pitchResult === "T") {
      eventType = "strike";
      eventColor = "bg-yellow-500";
      eventLabel = "스트라이크";
    } else if (pitchResult === "B") {
      eventType = "ball";
      eventColor = "bg-green-500";
      eventLabel = "";
    } else if (pitchResult === "H") {
      eventType = "hit";
      eventColor = "bg-blue-500";
      eventLabel = "타격";
    }

    return { pitchNumber, eventType, eventColor, eventLabel };
  };

  // 팀 문자열을 너그럽게 매칭하기 위한 정규화 도우미
  const normalizeTeamKey = (value?: string | null) =>
    (value ? value.toLowerCase().replace(/[^a-z0-9가-힣]/g, "") : "").trim();

  // team id/한국어 이름/영문 별칭 등을 모두 수용해 Team 객체를 찾는다
  const findTeamByAnyName = (teamName?: string | null) => {
    const normalized = normalizeTeamKey(teamName);
    if (!normalized) return undefined;

    return TEAMS.find((team) => {
      const candidates = [
        team.id,
        team.name,
        team.shortName,
        team.name.replace(/\s+/g, ""),
        team.shortName.replace(/\s+/g, ""),
      ]
        .map(normalizeTeamKey)
        .filter(Boolean);

      // "samsunglions", "kia tigers" 같은 케이스도 포괄하기 위해 contains 매칭을 허용
      return candidates.some(
        (candidate) =>
          candidate === normalized ||
          normalized === `${candidate}s` ||
          normalized.startsWith(candidate) ||
          normalized.endsWith(candidate),
      );
    });
  };

  const resolveTeamId = (teamName?: string | null) =>
    findTeamByAnyName(teamName)?.id || null;

  // 팀 이름으로 팀 정보 조회 (id/별칭 모두 허용)
  const getTeamInfo = (teamName?: string | null) => {
    const teamData = findTeamByAnyName(teamName);
    if (teamData) {
      return {
        color: teamData.color,
        shortName: teamData.shortName,
        id: teamData.id,
        name: teamData.name,
      };
    }
    // 기본값
    return {
      color: "#999",
      shortName: teamName || "팀",
      id: teamName || "unknown",
      name: teamName || "팀",
    };
  };

  // Orchestrator를 사용한 에이전트 대화 생성 (스트리밍) - 30초 인터벌에서만 호출
  const callOrchestrator = async (memoryToUse: Array<{speaker: string, text: string}>) => {
    setIsGenerating(true);
    const requestStartTime = Date.now(); // 요청 시작 시간 기록

    try {
      // localStorage에서 뉴스 데이터 읽기
      const newsDataStr = localStorage.getItem('gameNewsData');
      let newsData = {};
      
      if (newsDataStr) {
        try {
          newsData = JSON.parse(newsDataStr);
          console.log('📰 News data loaded from localStorage:', newsData);
        } catch (error) {
          console.error('❌ Failed to parse news data from localStorage:', error);
        }
      } else {
        console.warn('⚠️ No news data in localStorage');
      }

      // localStorage에서 에이전트 데이터 읽기
      let agents: any[] = [];
      try {
        const agentsStr = localStorage.getItem("ai-fan-agents");
        if (agentsStr) {
          agents = JSON.parse(agentsStr);
          console.log('👥 Agents loaded from localStorage:', agents);
        }
      } catch (error) {
        console.error('❌ Failed to parse agents from localStorage:', error);
      }

      // orchestrator 엔드포인트 호출
      const response = await fetch(`${API_URL}/orchestrate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          userMessages: memoryToUse,
          currGameStat: "경기 진행 중",
          gameFlow: "",
          newsData: newsData,
          agents: agents,
        }),
      });

      if (!response.ok) {
        throw new Error(`Server error: ${response.status}`);
      }

      // 스트리밍 응답 처리
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        throw new Error("No response body");
      }

      let buffer = "";
      let lineCount = 0;
      let parseErrorCount = 0;
      let requestStartTime = Date.now();
      let lastMessageDisplayTime = 0;

      console.log("[Orchestrator] Starting to read stream response");

      // 메시지 표시 함수
      const displayMessage = async (item: {speaker: string, text: string, team?: string}, arrivalTime: number) => {
        if (lastMessageDisplayTime === 0) {
          // 첫 메시지는 바로 표시
          console.log(`[Display] First message from "${item.speaker}" - displaying immediately`);
        } else {
          // 메시지 길이에 따라 목표 간격 계산 (1.5초 ~ 2.5초)
          const minInterval = 3500;
          const maxInterval = 4500;
          const avgTextLength = 100;
          
          const textLengthRatio = Math.min(item.text.length / avgTextLength, 2);
          const targetInterval = minInterval + (maxInterval - minInterval) * (textLengthRatio / 2);
          
          // 직전 메시지 표시로부터 경과 시간 계산
          const elapsedSinceLastDisplay = Date.now() - lastMessageDisplayTime;
          
          // 목표 간격에 미달하면 추가 딜레이
          const additionalDelay = Math.max(0, targetInterval - elapsedSinceLastDisplay);
          
          if (additionalDelay > 0) {
            console.log(`[Display] Message from "${item.speaker}" (${item.text.length} chars, target: ${targetInterval.toFixed(0)}ms) - ${elapsedSinceLastDisplay.toFixed(0)}ms elapsed, adding ${additionalDelay.toFixed(0)}ms delay`);
            await new Promise((resolve) => setTimeout(resolve, additionalDelay));
          } else {
            console.log(`[Display] Message from "${item.speaker}" (${item.text.length} chars, target: ${targetInterval.toFixed(0)}ms) - ${elapsedSinceLastDisplay.toFixed(0)}ms elapsed, displaying immediately`);
          }
        }

        // 메시지 표시
        const resolvedTeamId = resolveTeamId(item.team) || homeTeamId || awayTeamId || "samsung";
        const isHome = resolvedTeamId === homeTeamId;

        const agentMessage: ChatMessage = {
          id: Date.now().toString() + Math.random(),
          agentId: item.speaker,
          agentName: item.speaker,
          team: resolvedTeamId,
          isHome: isHome,
          message: item.text,
          timestamp: new Date().toLocaleTimeString(),
          avatarSeed: item.speaker,
        };

        setMessages((prev) => [...prev, agentMessage]);
        lastMessageDisplayTime = Date.now();
      };

      while (true) {
        const { done, value } = await reader.read();
        
        if (done) {
          const totalElapsedTime = Date.now() - requestStartTime;
          console.log(`[Orchestrator] Stream ended. Total lines processed: ${lineCount}, Parse errors: ${parseErrorCount}`);
          console.log(`⏱️ [Orchestrator] Total time from request start to all messages displayed: ${totalElapsedTime}ms (${(totalElapsedTime / 1000).toFixed(2)}s)`);
          break;
        }

        // 디코드하고 버퍼에 추가
        buffer += decoder.decode(value, { stream: true });
        console.log(buffer);
        // 줄 단위로 분리
        const lines = buffer.split("\n");
        buffer = lines.pop() || ""; // 마지막 불완전한 줄은 버퍼에 남김

        for (const line of lines) {
          if (line.trim()) {
            lineCount++;
            try {
              const messageData = JSON.parse(line);
              const speaker = messageData.speaker || "Unknown";
              const text = messageData.text || "";
              const team = messageData.team || "samsung lions";

              console.log(`[Orchestrator] Message ${lineCount}: speaker="${speaker}", textLength=${text.length}, team="${team}"`);

              // 메시지 도착 시간 기록하고 표시 (딜레이 포함)
              const arrivalTime = Date.now();
              await displayMessage({ speaker, text, team }, arrivalTime);

            } catch (e) {
              parseErrorCount++;
              console.error(`[Orchestrator] Parse error on line ${lineCount}:`, e);
              console.error(`[Orchestrator] Line content (first 200 chars):`, line.substring(0, 200));
            }
          }
        }
      }

    } catch (error) {
      console.error("Orchestrator API 오류:", error);
      
      // 에러 메시지 표시
      const errorMessage: ChatMessage = {
        id: Date.now().toString(),
        agentId: "system",
        agentName: "시스템",
        team: "samsung lions",
        isHome: true,
        message: "메시지를 생성할 수 없습니다. 다시 시도해주세요.",
        timestamp: new Date().toLocaleTimeString(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleSendMessage = () => {
    if (!inputMessage.trim()) return;
    
    const userMessage = inputMessage;
    setInputMessage("");
    
    // 사용자 팀 정보 결정
    const userTeamName = userTeam || selectedAgents[0]?.team || "samsung";
    const resolvedUserTeamId = resolveTeamId(userTeamName) || homeTeamId || awayTeamId || "samsung";
    const userIsHome = resolvedUserTeamId === homeTeamId;
    
    // 사용자 메시지를 UI에 표시
    const newUserMessage: ChatMessage = {
      id: Date.now().toString(),
      agentId: "user",
      agentName: "나",
      team: resolvedUserTeamId,
      isHome: userIsHome,
      message: userMessage,
      timestamp: new Date().toLocaleTimeString(),
    };
    setMessages((prev) => [...prev, newUserMessage]);
    
    // context_memory에만 추가 (다음 30초 주기에서 반영됨)
    setContextMemory(prev => [...prev, {
      speaker: "사용자",
      text: userMessage
    }]);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  // 15초마다 새로운 orchestrator 요청을 시작 (이전 요청 완료 후)
  useEffect(() => {
    let isActive = true;
    let requestCount = 0;
    let lastRequestStartTime = 0;

    const startOrchestratorRequest = async () => {
      if (!isActive) return;
      
      requestCount++;
      const currentRequestId = requestCount;
      
      // 이번 요청의 시작 시간 기록
      lastRequestStartTime = Date.now();
      
      console.log(`[Orchestrator] Starting request #${currentRequestId} at ${new Date(lastRequestStartTime).toLocaleTimeString()}`);
      
      try {
        await callOrchestrator(contextMemory);
        console.log(`[Orchestrator] Request #${currentRequestId} completed at ${new Date().toLocaleTimeString()}`);
      } catch (error) {
        console.error(`[Orchestrator] Request #${currentRequestId} failed:`, error);
      }

      // 첫 요청 시작으로부터 얼마나 경과했는지 확인
      const elapsedSinceRequestStart = Date.now() - lastRequestStartTime;
      const remainingTime = Math.max(0, 15000 - elapsedSinceRequestStart);

      if (remainingTime > 0) {
        console.log(`[Orchestrator] Request #${currentRequestId} completed after ${elapsedSinceRequestStart.toFixed(0)}ms. Waiting ${remainingTime.toFixed(0)}ms before next request`);
        await new Promise((resolve) => setTimeout(resolve, remainingTime));
      } else {
        console.log(`[Orchestrator] Request #${currentRequestId} completed after ${elapsedSinceRequestStart.toFixed(0)}ms. Starting next request immediately`);
      }

      // 다음 요청 시작 (재귀적으로)
      if (isActive) {
        startOrchestratorRequest();
      }
    };

    // 즉시 첫 요청 시작
    startOrchestratorRequest();

    // 클린업
    return () => {
      isActive = false;
    };
  }, []); // 빈 의존성 배열 - 마운트 시에만 설정

  // contextMemory 변경 시에도 inGenerating 상태 업데이트는 필요하지만,
  // 인터벌 재설정은 불필요 (이미 설정된 인터벌이 contextMemory를 캡처)

  useEffect(() => {
    if (chatRef.current && shouldAutoScrollRef.current) {
      chatRef.current.scrollTop = chatRef.current.scrollHeight;
    }
  }, [messages]);

  // 스크롤 이벤트 핸들러
  const handleChatScroll = () => {
    if (chatRef.current) {
      const element = chatRef.current;
      // 스크롤이 최하단인지 확인 (10px 여유 범위)
      const isAtBottom = element.scrollHeight - element.scrollTop - element.clientHeight < 10;
      
      // 최하단이면 자동 스크롤 재개, 아니면 중지
      shouldAutoScrollRef.current = isAtBottom;
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 p-6">
      <div className="max-w-7xl mx-auto space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <Button variant="outline" onClick={onBack}>
            <ArrowLeft className="size-4 mr-2" />
            에이전트 설정으로 돌아가기
          </Button>
          <div className="flex items-center gap-2">
            {selectedAgents.map((agent) => {
              const teamInfo = getTeamInfo(agent.team);
              return (
                <Badge
                  key={agent.id}
                  variant={
                    agent.isHome
                      ? "default"
                      : "secondary"
                  }
                  style={{
                    backgroundColor: teamInfo.color,
                    borderColor: teamInfo.color,
                    color: "white",
                  }}
                >
                  {agent.name}
                </Badge>
              );
            })}
          </div>
        </div>

        {/* Main Content */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Video Player */}
          <div className="lg:col-span-2">
            <Card className="h-[600px]">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Video className="size-5" />
                  경기 영상
                </CardTitle>
              </CardHeader>
              <CardContent className="h-[calc(100%-80px)]">
                <div className="w-full h-full bg-slate-900 rounded-lg flex items-center justify-center">
                  <div className="text-center space-y-4">
                    <Video className="size-16 mx-auto text-slate-600" />
                    <p className="text-slate-400">
                      경기 영상이 여기에 표시됩니다
                    </p>
                    <p className="text-slate-500 text-sm">
                      실제 구현 시 YouTube iframe 또는 video
                      태그가 들어갈 위치입니다
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Right Side: AI Fan Chat */}
          <div className="lg:col-span-1">
            <Card className="h-[600px] flex flex-col">
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
                <CardTitle className="text-base">
                  AI 팬 채팅
                </CardTitle>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    setShowAgentInfo(!showAgentInfo)
                  }
                  className="ml-auto"
                >
                  <Users className="size-4 mr-2" />
                  {showAgentInfo
                    ? "에이전트 숨기기"
                    : "에이전트 보기"}
                </Button>
              </CardHeader>
              <CardContent className="flex-1 flex flex-col gap-3 p-4 overflow-hidden min-h-0 relative">
                {/* Agent List Modal (full details) */}
                <Dialog open={showAgentInfo} onOpenChange={(open) => setShowAgentInfo(!!open)}>
                  <DialogContent className="max-w-[90vw] w-full sm:max-w-[90vw] max-h-[95vh] overflow-y-auto">
                    <DialogHeader>
                      <DialogTitle className="text-xl">에이전트 목록</DialogTitle>
                      <p className="text-sm text-muted-foreground mt-1">선택된 에이전트들의 상세 정보를 확인하세요.</p>
                    </DialogHeader>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 py-2">
                      {selectedAgents.map((agent) => (
                        <AgentCard
                          key={agent.id}
                          agent={agent}
                          onEdit={() => {}}
                          onDelete={() => {}}
                          homeTeamId={homeTeamId}
                          awayTeamId={awayTeamId}
                          readOnly={true}
                        />
                      ))}
                    </div>
                  </DialogContent>
                </Dialog>

                {/* Chat Messages */}
                <div
                  className="flex-1 overflow-y-auto space-y-2 pr-2"
                  ref={chatRef}
                  onScroll={handleChatScroll}
                >
                  {messages.length > 0 ? (
                    messages.map((msg) => {
                      const avatarUrl = msg.avatarSeed
                        ? `https://api.dicebear.com/7.x/avataaars/svg?seed=${msg.avatarSeed}`
                        : null;
                      const msgTeamInfo = getTeamInfo(msg.team);

                      return (
                        <div
                          key={msg.id}
                          className="bg-amber-50 border border-amber-200 rounded-lg p-3"
                        >
                          <div className="flex items-center gap-2 mb-1">
                            {avatarUrl && (
                              <img
                                src={avatarUrl}
                                alt={msg.agentName}
                                className="size-5 rounded-full bg-white flex-shrink-0"
                              />
                            )}
                            <span className="font-semibold text-xs">
                              {msg.agentName}
                            </span>
                            <Badge
                              variant={
                                msg.isHome
                                  ? "default"
                                  : "secondary"
                              }
                              className="text-xs"
                              style={{
                                backgroundColor:
                                  msgTeamInfo.color,
                                borderColor: msgTeamInfo.color,
                                color: "white",
                              }}
                            >
                              {msgTeamInfo.shortName}
                            </Badge>
                            <span className="text-xs text-muted-foreground ml-auto">
                              {msg.timestamp}
                            </span>
                          </div>
                          <p className="text-xs">
                            {msg.message}
                          </p>
                        </div>
                      );
                    })
                  ) : (
                    <div className="h-full flex items-center justify-center">
                      <p className="text-muted-foreground text-center text-sm">
                        AI 팬들의 응원이 시작됩니다!
                      </p>
                    </div>
                  )}
                </div>

                {/* Input */}
                <div className="flex gap-2">
                  <Input
                    placeholder="메시지를 입력하세요..."
                    value={inputMessage}
                    onChange={(e) =>
                      setInputMessage(e.target.value)
                    }
                    onKeyPress={handleKeyPress}
                    className="text-sm"
                  />
                  <Button
                    size="icon"
                    onClick={handleSendMessage}
                    disabled={!inputMessage.trim()}
                  >
                    <Send className="size-4" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>

        {/* Text Broadcast Section - Bottom */}
        <Card className="mt-4">
          <CardHeader>
            <CardTitle className="text-base">
              문자 중계
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4">
            <Tabs
              value={selectedInning}
              onValueChange={setSelectedInning}
            >
              <TabsList className="mb-3">
                {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((inning) => {
                  const hasData =
                    existingInnings.includes(inning);
                  return (
                    <TabsTrigger
                      key={inning}
                      value={inning.toString()}
                      disabled={!hasData}
                      className="disabled:opacity-40"
                    >
                      {inning}회
                    </TabsTrigger>
                  );
                })}
              </TabsList>

              {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((inning) => {
                // 해당 이닝의 초/말 데이터 가져오기
                const topHalfKey = `${inning}-초`;
                const bottomHalfKey = `${inning}-말`;
                const topHalfData =
                  groupedByInningAndHalf[topHalfKey] || [];
                const bottomHalfData =
                  groupedByInningAndHalf[bottomHalfKey] || [];

                const hasAnyData =
                  topHalfData.length > 0 ||
                  bottomHalfData.length > 0;

                // 렌더링 함수: 타자 목록 표시
                const renderBatters = (
                  halfData: PlayData[],
                ) => {
                  const groupedByBatter = halfData.reduce(
                    (acc, play) => {
                      const key = play.batterAppearanceOrder;
                      if (!acc[key]) {
                        acc[key] = [];
                      }
                      acc[key].push(play);
                      return acc;
                    },
                    {} as Record<number, PlayData[]>,
                  );

                  const sortedBatterKeys = Object.keys(
                    groupedByBatter,
                  )
                    .map(Number)
                    .sort((a, b) => b - a);

                  return sortedBatterKeys.map(
                    (batterOrder, groupIndex) => {
                      const plays =
                        groupedByBatter[batterOrder];
                      const battingInfo = plays[0];
                      
                      // 경기 종료 확인 ("=====" 포함 여부)
                      const hasGameEnd = plays.some((p) =>
                        p.seqDescription.includes("====="),
                      );
                      
                      // 경기 종료 이후 결과 데이터인 경우 (모든 이벤트가 결과 데이터)
                      if (hasGameEnd) {
                        return (
                          <div key={batterOrder} className="space-y-3">
                            {/* 경기 종료 헤더 */}
                            <div className="p-4 rounded-lg bg-gradient-to-r from-blue-600 to-blue-500 border-2 border-blue-700 shadow-lg">
                              <p className="text-lg font-bold text-white text-center">
                                ⚾ 경기가 종료되었습니다
                              </p>
                            </div>
                            
                            {/* 경기 결과 데이터 */}
                            {plays.map((play) => {
                              // "=====" 이벤트는 건너뛰기
                              if (play.seqDescription.includes("=====")) {
                                return null;
                              }
                              
                              // 경기 결과 데이터 표시
                              return (
                                <div
                                  key={play.seqNo}
                                  className="p-4 rounded-lg bg-blue-50 border-2 border-blue-300 shadow-sm"
                                >
                                  <p className="text-base font-bold text-blue-900">
                                    {play.seqDescription}
                                  </p>
                                </div>
                              );
                            })}
                          </div>
                        );
                      }
                      
                      // 모든 결과 이벤트 찾기 (seqDescription에 ":"가 포함된 데이터)
                      const resultPlays = plays.filter((p) =>
                        p.seqDescription.includes(":"),
                      );
                      // 결과가 없으면 진행 중이므로 자동으로 확장, 결과가 있으면 expandedBatters에 있을 때만 확장
                      const isExpanded = resultPlays.length > 0
                        ? expandedBatters.has(batterOrder)
                        : true;
                      const isLatest = groupIndex === 0;

                      return (
                        <div
                          key={batterOrder}
                          className="space-y-2"
                        >
                          {/* Batter Header */}
                          <button
                            onClick={() =>
                              toggleBatter(batterOrder)
                            }
                            className={`w-full p-3 rounded-lg border text-left transition-colors ${
                              isLatest
                                ? "bg-blue-50 border-blue-300 hover:bg-blue-100"
                                : "bg-slate-50 border-slate-300 hover:bg-slate-100"
                            }`}
                          >
                            <div className="flex items-center gap-2">
                              {isExpanded ? (
                                <ChevronDown className="size-4 flex-shrink-0 text-muted-foreground" />
                              ) : (
                                <ChevronRight className="size-4 flex-shrink-0 text-muted-foreground" />
                              )}
                              {resultPlays.length > 0 ? (
                                <div className="flex flex-col gap-1">
                                  {resultPlays.slice().reverse().map((resultPlay, idx) => (
                                    <span
                                      key={resultPlay.seqNo}
                                      className={`font-bold text-sm ${
                                        resultPlay.seqDescription.includes("홈런") ||
                                        resultPlay.seqDescription.includes("홈인")
                                          ? "text-blue-600"
                                          : isLatest
                                            ? "text-blue-900"
                                            : "text-slate-900"
                                      }`}
                                    >
                                      {resultPlay.seqDescription}
                                    </span>
                                  ))}
                                </div>
                              ) : (
                                <div className="flex flex-col gap-1">
                                  <div className="flex items-center gap-2">
                                    <span
                                      className={`font-bold text-sm ${isLatest ? "text-blue-900" : "text-slate-900"}`}
                                    >
                                      {battingInfo.batterName}
                                    </span>
                                    <span className="text-xs text-muted-foreground">
                                      {battingInfo.lineupSlot}번
                                    </span>
                                  </div>
                                  <div className="flex flex-wrap gap-1 text-xs text-slate-600">
                                    {plays
                                      .filter((p) => !p.seqDescription.includes(":"))
                                      .map((p, idx) => {
                                        const eventInfo = getEventInfo(
                                          p.seqDescription,
                                          p.pitchResult,
                                        );
                                        return (
                                          <span key={p.seqNo}>
                                            {eventInfo.eventLabel || p.seqDescription}
                                            {idx < plays.filter((p) => !p.seqDescription.includes(":")).length - 1 && ", "}
                                          </span>
                                        );
                                      })}
                                  </div>
                                </div>
                              )}
                            </div>
                          </button>

                          {/* Pitch Events */}
                          {isExpanded && (
                            <div className="ml-4 space-y-1">
                              {plays
                                .slice()
                                .reverse()
                                .map((play, idx) => {
                                  const eventInfo =
                                    getEventInfo(
                                      play.seqDescription,
                                      play.pitchResult,
                                    );

                                  // 각 타석에서 마지막 투구 이벤트 찾기
                                  const pitchEvents =
                                    plays.filter(
                                      (p) =>
                                        p.pitchType &&
                                        p.pitchSpeed > 0,
                                    );
                                  const lastPitchEvent =
                                    pitchEvents.length > 0
                                      ? pitchEvents[
                                          pitchEvents.length - 1
                                        ]
                                      : null;
                                  const isLastPitch =
                                    lastPitchEvent &&
                                    play.seqNo ===
                                      lastPitchEvent.seqNo;

                                  return (
                                    <div
                                      key={play.seqNo}
                                      className="p-2 rounded-lg bg-white border border-slate-200"
                                    >
                                      <div className="flex items-center gap-2 mb-1">
                                        {/* 최종 결과가 아닌 경우에만 구 번호 표시 */}
                                        {!play.seqDescription.includes(
                                          ":",
                                        ) &&
                                          eventInfo.pitchNumber &&
                                          eventInfo.eventLabel && (
                                            <div
                                              className={`${eventInfo.eventColor} rounded-full size-6 flex items-center justify-center text-white text-xs font-bold flex-shrink-0`}
                                            >
                                              {
                                                eventInfo.pitchNumber
                                              }
                                            </div>
                                          )}
                                        <p className="text-xs font-semibold text-slate-900">
                                          {/* 최종 결과(":"포함)는 seqDescription 그대로 표시 */}
                                          {play.seqDescription.includes(
                                            ":",
                                          )
                                            ? play.seqDescription
                                            : eventInfo.eventLabel ||
                                              play.seqDescription}
                                        </p>
                                      </div>

                                      {play.pitchType &&
                                        play.pitchSpeed > 0 &&
                                        !play.seqDescription.includes(
                                          ":",
                                        ) && (
                                          <div className="text-xs ml-8 text-muted-foreground">
                                            <span className="font-medium">
                                              {play.pitchSpeed}
                                              km/h
                                            </span>
                                            <span className="mx-1">
                                              |
                                            </span>
                                            <span>
                                              {play.pitchType}
                                            </span>
                                            {!isLastPitch && (
                                              <>
                                                <span className="mx-1">
                                                  |
                                                </span>
                                                <span>
                                                  {play.ballCount ||
                                                    `${play.ball} - ${play.strike}`}
                                                </span>
                                              </>
                                            )}
                                          </div>
                                        )}

                                      {(!play.pitchType ||
                                        play.pitchSpeed ===
                                          0) && (
                                        <div className="text-xs mt-1 text-muted-foreground">
                                          <span>
                                            투수:{" "}
                                            {play.pitcherName}
                                          </span>
                                        </div>
                                      )}
                                    </div>
                                  );
                                })}
                            </div>
                          )}
                        </div>
                      );
                    },
                  );
                };

                return (
                  <TabsContent
                    key={inning}
                    value={inning.toString()}
                  >
                    <div className="max-h-[400px] overflow-y-auto space-y-4 pr-2">
                      {hasAnyData ? (
                        <>
                          {/* 말 (홈팀 공격) */}
                          {bottomHalfData.length > 0 && (
                            <div className="space-y-3">
                              <div className="bg-white rounded-lg p-2 sticky top-0 z-20">
                                <div className="flex items-center justify-between">
                                  <span className="font-bold text-base text-slate-900">
                                    {inning}회 말 -{" "}
                                    {
                                      bottomHalfData[0]
                                        .offensiveTeam
                                    }{" "}
                                    공격
                                  </span>
                                </div>
                              </div>
                              {renderBatters(bottomHalfData)}
                            </div>
                          )}

                          {/* 초 (어웨이팀 공) */}
                          {topHalfData.length > 0 && (
                            <div className="space-y-3">
                              <div className="bg-white rounded-lg p-2 sticky top-0 z-20">
                                <div className="flex items-center justify-between">
                                  <span className="font-bold text-base text-slate-900">
                                    {inning}회 초 -{" "}
                                    {
                                      topHalfData[0]
                                        .offensiveTeam
                                    }{" "}
                                    공격
                                  </span>
                                </div>
                              </div>
                              {renderBatters(topHalfData)}
                            </div>
                          )}
                        </>
                      ) : (
                        <div className="h-[200px] flex items-center justify-center">
                          <p className="text-muted-foreground text-center text-sm">
                            {inning}회 데이터가 없습니다
                          </p>
                        </div>
                      )}
                    </div>
                  </TabsContent>
                );
              })}
            </Tabs>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}