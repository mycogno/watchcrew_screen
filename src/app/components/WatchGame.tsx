import { useState, useEffect, useRef } from "react";
import { Agent } from "./AgentCard";
import { Button } from "./ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "./ui/card";
import { Input } from "./ui/input";
import { Badge } from "./ui/badge";
import {
  ArrowLeft,
  Send,
  Video,
  Users,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { TEAMS } from "./TeamSelection";
import OpenAI from "openai";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "./ui/tabs";
import { playHistoryData } from "../data/playHistory";

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
  team: string;
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
  const [expandedBatters, setExpandedBatters] = useState<
    Set<number>
  >(new Set()); // 확장된 타자 목록 (batterAppearanceOrder 기준) - 초기값 비움
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

  // OpenAI 클라이언트 초기화
  // Vite 환경에서 OpenAI API 키를 가져옵니다 (브라우저)
  const OPENAI_API_KEY = import.meta.env.VITE_OPENAI_API_KEY;

  const openai = new OpenAI({
    apiKey: OPENAI_API_KEY,
    dangerouslyAllowBrowser: true, // 클라이언트 사이드에서 사용 (프로덕션에서는 백엔드 권장)
  });

  const getTeamInfo = (team: "home" | "away") => {
    const teamData = team === "home" ? homeTeam : awayTeam;
    return {
      color:
        teamData?.color ||
        (team === "home" ? "#074CA1" : "#EA0029"),
      shortName:
        teamData?.shortName ||
        (team === "home" ? "홈팀" : "어웨이팀"),
    };
  };

  // 에이전트 메시지 생성 함수
  const generateAgentMessage = async (
    agent: Agent,
    conversationHistory: ChatMessage[],
  ) => {
    try {
      // 에이전트가 응원하는 팀 정보 가져오기
      const teamId =
        agent.team === "home" ? homeTeamId : awayTeamId;
      const team = TEAMS.find((t) => t.id === teamId);
      const teamName =
        team?.name ||
        (agent.team === "home" ? "홈팀" : "어웨이팀");

      // 대화 히스토리를 OpenAI API 포맷으로 변환
      const historyMessages = conversationHistory.map(
        (msg) => ({
          role: "user" as const,
          content: `[${msg.agentName}]: ${msg.message}`,
        }),
      );

      const messages = [
        {
          role: "system" as const,
          content: `당신은 ${teamName}의 팬입니다. 당신은 프로야구 경기를 시청하는 중입니다. 당신의 성격: ${agent.prompt}. 이전 메시지를 고려하여 채팅 메시지를 생성하시오. 응답은 한국어로 하며, 짧고 자연스러운 채팅 형식으로 작성하세요 (1-2문장).`,
        },
        ...historyMessages,
      ];

      // 디버깅: OpenAI에 전달되는 메시지 출력
      console.log(`[${agent.name}] OpenAI API 요청:`, {
        agent: agent.name,
        team: teamName,
        messages: messages,
      });

      const response = await openai.chat.completions.create({
        model: "gpt-4.1",
        messages: messages,
        max_tokens: 100,
        temperature: 0.9,
      });

      const generatedMessage =
        response.choices[0]?.message?.content || "...";

      // 디버깅: 생성된 응답 출력
      console.log(
        `[${agent.name}] 생성된 응답:`,
        generatedMessage,
      );

      return generatedMessage;
    } catch (error) {
      console.error("OpenAI API 오류:", error);
      return "메시지를 생성할 수 없습니다.";
    }
  };

  // 모든 에이전트가 순차적으로 응답하도록 처리
  const generateAllAgentResponses = async (
    userMessage: string,
  ) => {
    setIsGenerating(true);

    // 사용자 메시지를 먼저 추가
    const newUserMessage: ChatMessage = {
      id: Date.now().toString(),
      agentId: "user",
      agentName: "나",
      team: userTeam || selectedAgents[0].team,
      message: userMessage,
      timestamp: new Date().toLocaleTimeString(),
    };

    setMessages((prev) => [...prev, newUserMessage]);

    // 현재까지의 대화 히스토리
    let currentHistory = [...messages, newUserMessage];

    // 에이전트 순서를 랜덤으로 섞기
    const shuffledAgents = [...selectedAgents].sort(
      () => Math.random() - 0.5,
    );

    // 각 에이전트가 순차적으로 응답 생성
    for (const agent of shuffledAgents) {
      // AI 응답 생성
      const generatedMessage = await generateAgentMessage(
        agent,
        currentHistory,
      );

      // 실제 메시지 추가
      const agentMessage: ChatMessage = {
        id: Date.now().toString() + agent.id,
        agentId: agent.id,
        agentName: agent.name,
        team: agent.team,
        message: generatedMessage,
        timestamp: new Date().toLocaleTimeString(),
        avatarSeed: agent.avatarSeed,
      };

      setMessages((prev) => [...prev, agentMessage]);

      // 현재 히스토리에 추가
      currentHistory = [...currentHistory, agentMessage];
    }

    setIsGenerating(false);
  };

  const handleSendMessage = async () => {
    if (inputMessage.trim() && !isGenerating) {
      const userMessage = inputMessage;
      setInputMessage("");
      await generateAllAgentResponses(userMessage);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTop = chatRef.current.scrollHeight;
    }
  }, [messages]);

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
                    agent.team === "home"
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
                {/* Agent Info Panel */}
                {showAgentInfo && (
                  <div className="absolute top-0 left-0 right-0 z-10 bg-white shadow-lg rounded-lg m-4 p-4 space-y-2 border">
                    <p className="text-xs font-semibold text-muted-foreground">
                      활성화된 AI 팬 ({selectedAgents.length}명)
                    </p>
                    <div className="space-y-2 max-h-[200px] overflow-y-auto pr-2">
                      {selectedAgents.map((agent) => {
                        const avatarUrl = `https://api.dicebear.com/7.x/avataaars/svg?seed=${agent.avatarSeed}`;
                        const teamInfo = getTeamInfo(
                          agent.team,
                        );

                        return (
                          <div
                            key={agent.id}
                            className="p-2 bg-slate-50 rounded-lg space-y-1"
                          >
                            <div className="flex items-center gap-2">
                              <img
                                src={avatarUrl}
                                alt={agent.name}
                                className="size-6 rounded-full bg-white flex-shrink-0"
                              />
                              <span className="font-semibold text-sm">
                                {agent.name}
                              </span>
                              <Badge
                                variant={
                                  agent.team === "home"
                                    ? "default"
                                    : "secondary"
                                }
                                className="text-xs"
                                style={{
                                  backgroundColor:
                                    teamInfo.color,
                                  borderColor: teamInfo.color,
                                  color: "white",
                                }}
                              >
                                {teamInfo.shortName}
                              </Badge>
                            </div>
                            <p className="text-xs text-muted-foreground pl-8">
                              {agent.prompt}
                            </p>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Chat Messages */}
                <div
                  className="flex-1 overflow-y-auto space-y-2 pr-2"
                  ref={chatRef}
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
                                msg.team === "home"
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
                    disabled={
                      !inputMessage.trim() || isGenerating
                    }
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