# LookFind Frontend

사진을 업로드하거나 카메라(`getUserMedia`)로 찍으면 백엔드(`../backend`)의 `POST /api/search`로 상의 유사 상품을 검색하는 Next.js 앱입니다.

- `app/components/look-find-app.tsx`: 홈·업로드(카메라)·RESULTS·ARCHIVE·SAVED·MY PAGE 화면
- `app/components/auth-form.tsx`, `login-curtain.tsx`: 이메일/카카오 로그인, 회원가입, 비밀번호 재설정
- `app/apis/backend.ts`: 백엔드 API 클라이언트 (검색, 계정, 검색 기록, 찜)
- `app/api/auth/kakao/*`: 카카오 OAuth 리다이렉트를 백엔드로 전달하는 라우트 핸들러

```bash
cp .env.example .env.local   # BACKEND_URL: 백엔드 주소
npm install
npm run dev                  # http://localhost:3000
```

`next.config.ts`가 `/api/*`, `/media/*`를 `BACKEND_URL`로 전달하므로 브라우저는 같은 출처로만 호출하고, 로그인 세션은 HttpOnly 쿠키(`lookfind_session`)로 유지됩니다. CORS 설정이 필요 없고 토큰이 JavaScript에 노출되지 않습니다.

- LOGIN → SIGN UP에서 이메일과 8~128자 비밀번호로 가입하면 자동 로그인됩니다. KAKAO로 계속하기는 백엔드 `KAKAO_CLIENT_ID`가 설정돼 있어야 합니다.
- 로그인 상태에서 완료된 검색만 ARCHIVE에 저장됩니다. 개별/전체 삭제 후 10분 안에 RETURN으로 복원할 수 있습니다.
- SAVED(찜)는 계정별로 서버 DB에 저장됩니다.
- 카메라는 보안 컨텍스트(localhost 또는 HTTPS)에서만 열립니다.

검증: `npm run lint`, `npx tsc --noEmit`, `npm run build`. 로컬 Turbopack 포트 오류를 피하려고 프로덕션 빌드는 Webpack을 사용합니다.
