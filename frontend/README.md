# LookFind Frontend

사진을 업로드하거나 카메라(`getUserMedia`)로 찍으면 백엔드(`../backend`)의 `POST /api/search`로 상의 유사 상품을 검색하는 Next.js 앱입니다.

- `app/components/look-find-app.tsx`: 홈·업로드(카메라)·RESULTS·ARCHIVE·SAVED·LOGIN 화면
- `app/apis/backend.ts`: 백엔드 API 클라이언트 (검색, 회원가입·로그인, 검색 기록, 찜). 브라우저에는 로그인 토큰만 저장하고 기록·찜은 서버 DB에 있습니다.

```bash
cp .env.example .env.local   # NEXT_PUBLIC_API_URL: 백엔드 주소
npm install
npm run dev                  # http://localhost:3000
```

브라우저가 백엔드를 직접 호출하므로 백엔드 `.env`의 `CORS_ORIGINS`에 프런트엔드 origin(`http://localhost:3000`, 배포 도메인)을 넣어야 합니다. 카메라는 보안 컨텍스트(localhost 또는 HTTPS)에서만 열립니다. `NEXT_PUBLIC_*` 값은 빌드 시점에 고정되므로 배포 환경에서는 빌드 전에 설정합니다.
