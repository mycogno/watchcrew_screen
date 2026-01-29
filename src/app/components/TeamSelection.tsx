import { useState } from "react";
import { Card, CardContent } from "./ui/card";
import { Button } from "./ui/button";
import { Trophy, ChevronRight } from "lucide-react";
import { ImageWithFallback } from "./figma/ImageWithFallback";
import { AnimatePresence, motion } from "motion/react";
import samsungLogo from "../../assets/874a11a99b89be3a71a2b277829f42896b7c1a3e.png";
import kiaLogo from "../../assets/ad6932e734bbd147d58bf54adc70d8318382e377.png";
import lgLogo from "../../assets/bc63019987c3fb3bd9d9b29b25a2f51005c1032f.png";
import doosanLogo from "../../assets/7d5d1e4d2920328bf1aa564e5c2661d637ccff60.png";
import ssgLogo from "../../assets/1e5ff3d49cd94987897fd984508c65328dd39c5b.png";
import ktLogo from "../../assets/685647917514c9ca3fce1d97014fda4f03b1b77d.png";
import ncLogo from "../../assets/2dcf0152fd86c25618753cffb1c62be4af7faf62.png";
import hanwhaLogo from "../../assets/05d0e3784218730e6a6ed9c8daf3ceddb633ba79.png";
import lotteLogo from "../../assets/3286ff03c716c04a668e7e131d7cde6ea7c3bd72.png";
import kiwoomLogo from "../../assets/204217256771822fd1160a5d5b7878c27b2da2df.png";

export interface Team {
  id: string;
  name: string;
  shortName: string;
  color: string;
  logo?: string;
}

export type MotivationLevel = "상" | "중" | "하";

export type MotivationSelection = Record<
  "shareFeelings" | "belonging" | "infoSharing" | "fun" | "emotionRelease",
  MotivationLevel
>;

const MOTIVATION_ITEMS: Array<{ key: keyof MotivationSelection; label: string }> = [
  { key: "shareFeelings", label: "감정 & 생각 나누기" },
  { key: "belonging", label: "소속감 형성" },
  { key: "infoSharing", label: "정보 공유" },
  { key: "fun", label: "재미와 즐거움" },
  { key: "emotionRelease", label: "감정 해소" },
];

export const TEAMS: Team[] = [
  { id: 'samsung', name: '삼성 라이온즈', shortName: '삼성', color: '#074CA1', logo: samsungLogo },
  { id: 'kia', name: 'KIA 타이거즈', shortName: 'KIA', color: '#EA0029', logo: kiaLogo },
  { id: 'lg', name: 'LG 트윈스', shortName: 'LG', color: '#C30452', logo: lgLogo },
  { id: 'doosan', name: '두산 베어스', shortName: '두산', color: '#131230', logo: doosanLogo },
  { id: 'ssg', name: 'SSG 랜더스', shortName: 'SSG', color: '#CE0E2D', logo: ssgLogo },
  { id: 'kt', name: 'kt wiz', shortName: 'kt', color: '#000000', logo: ktLogo },
  { id: 'nc', name: 'NC 다이노스', shortName: 'NC', color: '#1D467F', logo: ncLogo },
  { id: 'hanwha', name: '한화 이글스', shortName: '한화', color: '#FF6600', logo: hanwhaLogo },
  { id: 'lotte', name: '롯데 자이언츠', shortName: '롯데', color: '#041E42', logo: lotteLogo },
  { id: 'kiwoom', name: '키움 히어로즈', shortName: '키움', color: '#820024', logo: kiwoomLogo },
];

export interface Game {
  id: string;
  awayTeamId: string; // vs 왼쪽 (어웨이)
  homeTeamId: string; // vs 오른쪽 (홈)
}

export const GAMES: Game[] = [
  { id: 'game1', awayTeamId: 'kia', homeTeamId: 'samsung' },
  { id: 'game2', awayTeamId: 'lg', homeTeamId: 'nc' },
  { id: 'game3', awayTeamId: 'lotte', homeTeamId: 'hanwha' },
  { id: 'game4', awayTeamId: 'kiwoom', homeTeamId: 'kt' },
  { id: 'game5', awayTeamId: 'doosan', homeTeamId: 'ssg' },
];

interface TeamSelectionProps {
  onSelectTeams: (
    homeTeamId: string,
    awayTeamId: string,
    userTeam: string,
    motivations: MotivationSelection
  ) => void;
}

export function TeamSelection({ onSelectTeams }: TeamSelectionProps) {
  const [selectedGame, setSelectedGame] = useState<string | null>(null);
  const [userTeam, setUserTeam] = useState<string | null>(null);
  const [motivations, setMotivations] = useState<MotivationSelection>({
    shareFeelings: "중",
    belonging: "중",
    infoSharing: "중",
    fun: "중",
    emotionRelease: "중",
  });
  const [selectionLocked, setSelectionLocked] = useState(false);

  const resetMotivations = () => {
    setMotivations({
      shareFeelings: "중",
      belonging: "중",
      infoSharing: "중",
      fun: "중",
      emotionRelease: "중",
    });
  };

  const resetSelection = () => {
    setSelectedGame(null);
    setUserTeam(null);
    resetMotivations();
    setSelectionLocked(false);
  };

  const handleSelectGame = (gameId: string) => {
    // 잠금 상태에서 동일 카드 클릭 시 선택 해제
    if (selectionLocked && selectedGame === gameId) {
      resetSelection();
      return;
    }

    setSelectedGame(gameId);
    setUserTeam(null); // 새 경기 선택 시 응원팀 초기화
    resetMotivations();
    setSelectionLocked(true);
  };

  const handleMotivationChange = (key: keyof MotivationSelection, level: MotivationLevel) => {
    setMotivations((prev) => ({ ...prev, [key]: level }));
  };

  const handleConfirm = () => {
    if (selectedGame && userTeam) {
      const game = GAMES.find(g => g.id === selectedGame);
      if (game) {
        onSelectTeams(game.homeTeamId, game.awayTeamId, userTeam, motivations);
      }
    }
  };

  const selectedGameData = selectedGame ? GAMES.find(g => g.id === selectedGame) : null;
  const awayTeam = selectedGameData ? TEAMS.find(t => t.id === selectedGameData.awayTeamId) : null;
  const homeTeam = selectedGameData ? TEAMS.find(t => t.id === selectedGameData.homeTeamId) : null;
  const visibleGames = selectionLocked && selectedGame ? GAMES.filter(g => g.id === selectedGame) : GAMES;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 flex items-center justify-center p-6">
      <div className="max-w-5xl w-full space-y-8">
        {/* Header */}
        <div className="text-center space-y-4">
          <div className="flex items-center justify-center">
            <Trophy className="size-16 text-primary" />
          </div>
          <h1 className="text-primary">AI 팬 에이전트와 함께하는 경기 관람</h1>
          <p className="text-muted-foreground">
            관람하실 경기를 선택하세요
          </p>
        </div>

        {/* 경기 선택 */}
        <div className="space-y-4">
          <AnimatePresence mode="popLayout" initial={false}>
            {visibleGames.map((game) => {
            const awayTeam = TEAMS.find(t => t.id === game.awayTeamId);
            const homeTeam = TEAMS.find(t => t.id === game.homeTeamId);
            const isSelected = selectedGame === game.id;

            if (!awayTeam || !homeTeam) return null;

            return (
              <motion.div
                key={game.id}
                layout
                initial={{ opacity: 0, y: 8, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1, transition: { duration: 0.2 } }}
                exit={{ opacity: 0, y: -8, scale: 0.98, height: 0, margin: 0, transition: { duration: 0.18 } }}
              >
                <Card
                  className={`group cursor-pointer transition-all hover:shadow-lg border-2 overflow-hidden relative ${
                    isSelected ? 'ring-4 ring-primary ring-offset-2 scale-[1.01]' : 'hover:scale-[1.005]'
                  }`}
                  style={{
                    borderColor: isSelected ? '#0ea5e9' : 'transparent',
                  }}
                  onClick={() => handleSelectGame(game.id)}
                >
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between gap-6">
                    {/* 어웨이팀 */}
                    <div className="flex-1 flex items-center gap-3">
                      <div className="w-16 h-16 flex items-center justify-center bg-white rounded-lg p-2 shadow-sm flex-shrink-0">
                        {awayTeam.logo ? (
                          <ImageWithFallback 
                            src={awayTeam.logo} 
                            alt={awayTeam.name} 
                            className="w-full h-full object-contain" 
                          />
                        ) : (
                          <span className="font-bold text-xl" style={{ color: awayTeam.color }}>
                            {awayTeam.shortName}
                          </span>
                        )}
                      </div>
                      <div className="text-left">
                        <h3 className="font-bold" style={{ color: awayTeam.color }}>
                          {awayTeam.name}
                        </h3>
                        <p className="text-xs text-muted-foreground mt-0.5">어웨이</p>
                      </div>
                    </div>

                    {/* VS */}
                    <div className="flex items-center">
                      <span className="text-2xl font-bold text-slate-400">VS</span>
                    </div>

                    {/* 홈팀 */}
                    <div className="flex-1 flex items-center gap-3 flex-row-reverse">
                      <div className="w-16 h-16 flex items-center justify-center bg-white rounded-lg p-2 shadow-sm flex-shrink-0">
                        {homeTeam.logo ? (
                          <ImageWithFallback 
                            src={homeTeam.logo} 
                            alt={homeTeam.name} 
                            className="w-full h-full object-contain" 
                          />
                        ) : (
                          <span className="font-bold text-xl" style={{ color: homeTeam.color }}>
                            {homeTeam.shortName}
                          </span>
                        )}
                      </div>
                      <div className="text-right">
                        <h3 className="font-bold" style={{ color: homeTeam.color }}>
                          {homeTeam.name}
                        </h3>
                        <p className="text-xs text-muted-foreground mt-0.5">홈</p>
                      </div>
                    </div>

                    {/* 선택됨 배지 */}
                    {isSelected && (
                      <div className="absolute top-2 right-2">
                        <div className="bg-primary text-white px-2 py-0.5 rounded-full text-xs font-semibold">
                          선택됨
                        </div>
                      </div>
                    )}
                  </div>
                  </CardContent>
                </Card>
              </motion.div>
            );
          })}
          </AnimatePresence>
        </div>

        {selectionLocked && selectedGame && (
          <div className="flex justify-end">
            <Button variant="outline" size="sm" onClick={resetSelection}>
              다른 경기 선택하기
            </Button>
          </div>
        )}

        {/* 응원팀 선택 */}
        {selectedGame && (
          <div className="space-y-4">
            <div className="text-center">
              <p className="font-medium text-base">어떤 팀을 응원하시나요?</p>
            </div>
            <div className="flex justify-center items-center gap-4">
              <Card 
                className={`cursor-pointer transition-all hover:shadow-lg border-2 w-48 ${
                  userTeam === awayTeam?.id ? 'ring-4 ring-primary ring-offset-2 scale-105' : 'hover:scale-105'
                }`}
                style={{
                  borderColor: userTeam === awayTeam?.id ? awayTeam?.color : '#e2e8f0',
                }}
                onClick={() => setUserTeam(awayTeam?.id || '')}
              >
                <CardContent className="p-4 flex flex-col items-center gap-3">
                  <div className="w-16 h-16 flex items-center justify-center bg-white rounded-lg p-2 shadow-sm">
                    {awayTeam?.logo ? (
                      <ImageWithFallback 
                        src={awayTeam.logo} 
                        alt={awayTeam.name} 
                        className="w-full h-full object-contain" 
                      />
                    ) : (
                      <span className="font-bold text-xl" style={{ color: awayTeam?.color }}>
                        {awayTeam?.shortName}
                      </span>
                    )}
                  </div>
                  <h3 className="font-bold text-center" style={{ color: awayTeam?.color }}>
                    {awayTeam?.name}
                  </h3>
                  {userTeam === awayTeam?.id && (
                    <div className="bg-primary text-white px-3 py-1 rounded-full text-xs font-semibold">
                      선택됨
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card 
                className={`cursor-pointer transition-all hover:shadow-lg border-2 w-48 ${
                  userTeam === homeTeam?.id ? 'ring-4 ring-primary ring-offset-2 scale-105' : 'hover:scale-105'
                }`}
                style={{
                  borderColor: userTeam === homeTeam?.id ? homeTeam?.color : '#e2e8f0',
                }}
                onClick={() => setUserTeam(homeTeam?.id || '')}
              >
                <CardContent className="p-4 flex flex-col items-center gap-3">
                  <div className="w-16 h-16 flex items-center justify-center bg-white rounded-lg p-2 shadow-sm">
                    {homeTeam?.logo ? (
                      <ImageWithFallback 
                        src={homeTeam.logo} 
                        alt={homeTeam.name} 
                        className="w-full h-full object-contain" 
                      />
                    ) : (
                      <span className="font-bold text-xl" style={{ color: homeTeam?.color }}>
                        {homeTeam?.shortName}
                      </span>
                    )}
                  </div>
                  <h3 className="font-bold text-center" style={{ color: homeTeam?.color }}>
                    {homeTeam?.name}
                  </h3>
                  {userTeam === homeTeam?.id && (
                    <div className="bg-primary text-white px-3 py-1 rounded-full text-xs font-semibold">
                      선택됨
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          </div>
        )}

        {/* 시청 동기 선택 */}
        {selectedGame && (
          <div className="space-y-3">
            <div className="text-center">
              <p className="font-medium text-base">경기 시청 동기(상/중/하)를 선택하세요</p>
              <p className="text-sm text-muted-foreground">각 항목별 중요도는 경기 중 에이전트 채팅 생성에 활용될 예정입니다.</p>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {MOTIVATION_ITEMS.map((item) => (
                <Card key={item.key} className="border-2">
                  <CardContent className="p-4 flex items-center justify-between gap-3">
                    <div className="flex flex-col">
                      <span className="font-semibold">{item.label}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      {["상", "중", "하"].map((level) => {
                        const isActive = motivations[item.key] === level;
                        return (
                          <Button
                            key={level}
                            size="sm"
                            variant={isActive ? "default" : "outline"}
                            onClick={() => handleMotivationChange(item.key, level as MotivationLevel)}
                          >
                            {level}
                          </Button>
                        );
                      })}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        )}

        {/* 확인 버튼 */}
        <div className="flex justify-center pt-4">
          <Button 
            size="lg"
            onClick={handleConfirm}
            disabled={!selectedGame || !userTeam}
            className="px-12"
          >
            <ChevronRight className="size-5 mr-2" />
            AI 팬 에이전트 설정하기
          </Button>
        </div>

        {/* Info */}
        <div className="text-center text-sm text-muted-foreground">
          <p>경기를 선택하면 다음 단계로 진행할 수 있습니다</p>
        </div>
      </div>
    </div>
  );
}
