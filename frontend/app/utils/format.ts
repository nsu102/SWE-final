export const won = (value: number | null) => value == null ? "가격 정보 없음" : `${new Intl.NumberFormat("ko-KR").format(value)}원`;
export const dateTime = (iso: string) => new Date(iso).toLocaleString("ko-KR");
export const similarityPercent = (similarity: number) => `${Math.round(similarity * 100)}%`;
