# 🎬 뉴스 요약 기능 통합 가이드

## 📋 개요

사용자가 경기를 선택하면 뉴스 데이터를 요청하여 localStorage에 저장하고, 경기 시청 화면에서 orchestrator가 뉴스를 참고하여 대화를 생성합니다.

---

## 🔄 데이터 플로우

```
1. TeamSelection에서 경기 선택
   ↓
2. /get_news_summary 요청 (game ID)
   ↓
3. 뉴스 요약 데이터 받음
   ↓
4. localStorage에 저장 (키: 'gameNewsData')
   ↓
5. AgentCreator 화면 이동 (데이터 유지)
   ↓
6. WatchGame에서 localStorage에서 읽기
   ↓
7. orchestrate 요청시 newsData 함께 전송
```

---

## 🔧 백엔드 구현 완료 ✅

### 새로운 엔드포인트
**POST `/get_news_summary`**

**요청:**
```json
{
  "game": "250523_HTSS_HT_game"
}
```

**응답:**
```json
{
  "Kia Tigers": "최근 KIA 타이거즈 뉴스 요약...",
  "Samsung Lions": "최근 삼성 라이온즈 뉴스 요약..."
}
```

### OrchestratorRequest 업데이트
```python
newsData: Optional[Dict[str, str]] = {}  # 뉴스 요약 데이터
```

### 프롬프트에 뉴스 통합
```
[주어진 데이터]
# Recent News
: {request.newsData}
```

---

## 💻 프론트엔드 구현 필요 부분

### 1. **TeamSelection.tsx 수정**

**뉴스 요청 추가:**
```typescript
// onSelectTeams 핸들러에 추가
const handleTeamsSelected = async (homeId: string, awayId: string, userTeamId: string) => {
  const gameId = `${selectedGameData.gameDate}_${homeId}_${awayId}_game`;
  
  try {
    // 뉴스 데이터 요청
    const newsResponse = await fetch(`${API_URL}/get_news_summary`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ game: gameId })
    });
    
    if (newsResponse.ok) {
      const newsData = await newsResponse.json();
      // localStorage에 저장
      localStorage.setItem('gameNewsData', JSON.stringify(newsData));
    }
  } catch (error) {
    console.error("Failed to fetch news summary:", error);
  }
  
  // 기존 로직 계속
  onSelectTeams(homeId, awayId, userTeamId);
};
```

### 2. **App.tsx에서 localStorage 초기화**

```typescript
const handleBackToTeamSelection = () => {
  // 기존 에이전트 초기화 로직...
  
  // ✨ 뉴스 데이터 초기화
  localStorage.removeItem('gameNewsData');
  
  // ... 나머지 로직
};
```

### 3. **WatchGame.tsx 수정**

**orchestrator 요청시 뉴스 데이터 포함:**
```typescript
const callOrchestrator = async (memoryToUse: Array<{speaker: string, text: string}>) => {
  // localStorage에서 뉴스 데이터 읽기
  const newsDataJson = localStorage.getItem('gameNewsData');
  const newsData = newsDataJson ? JSON.parse(newsDataJson) : {};
  
  const response = await fetch(`${API_URL}/orchestrate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      userMessages: memoryToUse,
      currGameStat: "경기 진행 중",
      gameFlow: "",
      newsData: newsData  // ✨ 뉴스 데이터 추가
    })
  });
  
  // 나머지 스트리밍 처리...
};
```

---

## 📊 localStorage 구조

**키:** `gameNewsData`

**값:**
```json
{
  "Kia Tigers": "KIA 타이거즈는 최근 3경기 중 2경기를 승리하며 상승세를 보이고 있습니다...",
  "Samsung Lions": "삼성 라이온즈는 투수진의 부상으로 인해 어려움을 겪고 있습니다..."
}
```

---

## 🎯 구현 순서

1. **TeamSelection.tsx** - 뉴스 요청 로직 추가
2. **App.tsx** - localStorage 초기화 로직 추가
3. **WatchGame.tsx** - newsData 읽기 및 전송 로직 추가
4. 테스트

---

## ⚠️ 주의사항

- **에러 처리**: 뉴스 요청 실패 시 빈 객체 `{}` 반환하도록 처리
- **CSV 경로**: 뉴스 CSV 파일이 올바른 위치에 있는지 확인
- **게임 포맷**: `YYYYMMDD_HOMEID_AWAYID_game` 정확히 맞아야 함

---

## 🧪 테스트 체크리스트

- [ ] 경기 선택 후 뉴스 요청 확인 (DevTools Network 탭)
- [ ] localStorage에 뉴스 데이터 저장 확인
- [ ] 경기 다시 선택시 이전 뉴스 데이터 초기화 확인
- [ ] WatchGame에서 orchestrator 요청에 newsData 포함 확인
- [ ] 뉴스를 참고한 대화 생성 확인
