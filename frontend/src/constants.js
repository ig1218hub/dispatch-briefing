export const DISPATCH = {
  now: { label: "🔴 지금 바로 출동", order: 0 },
  remote: { label: "🟡 원격 조치 먼저", order: 1 },
  later: { label: "🟢 다음 정기점검", order: 2 },
};
export const LEVEL = { L1: "근거", L2: "추정(전체 통계)", L3: "이력 없음" };
export const GRADE = { Critical: 0, Major: 1, Minor: 2, Warning: 3 };
