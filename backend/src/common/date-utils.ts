// 统一按业务所在地区时区（尼日利亚 Africa/Lagos，UTC+1，无夏令时）处理"日期属于哪一天"的边界判断，
// 而不是依赖服务器进程自身的系统时区（云端部署通常是 UTC），避免出现日期错位（见需求反馈 2.5）。
const BUSINESS_UTC_OFFSET_MINUTES = 60;

// 给定任意时间点，返回该时间点在业务时区下所属"自然日"的 UTC 零点表示（用于 @db.Date 字段存取/比较）
export function toBusinessDateOnly(input: Date | string): Date {
  const d = typeof input === 'string' ? new Date(input) : input;
  const shifted = new Date(d.getTime() + BUSINESS_UTC_OFFSET_MINUTES * 60000);
  return new Date(Date.UTC(shifted.getUTCFullYear(), shifted.getUTCMonth(), shifted.getUTCDate()));
}

// 业务时区下的"当前时间点"所属自然日
export function businessToday(): Date {
  return toBusinessDateOnly(new Date());
}

// 按业务时区自然日，从 start 到 end（含）逐天枚举
export function eachBusinessDate(start: Date | string, end: Date | string): Date[] {
  const days: Date[] = [];
  const cur = toBusinessDateOnly(start);
  const last = toBusinessDateOnly(end);
  while (cur <= last) {
    days.push(new Date(cur));
    cur.setUTCDate(cur.getUTCDate() + 1);
  }
  return days;
}

// 将 "HH:mm" 规则时间（业务时区）与某个业务自然日组合成实际 UTC 时间点，用于和 clockInAt 等时间戳比较
export function combineBusinessDateAndTime(businessDate: Date, hhmm: string): Date {
  const [h, m] = hhmm.split(':').map(Number);
  // businessDate 是当天在业务时区的零点对应的 UTC 时间；加上 hh:mm，再减去业务时区偏移，得到真实 UTC 时间点
  const utcMillis = businessDate.getTime() + (h * 60 + m) * 60000 - BUSINESS_UTC_OFFSET_MINUTES * 60000;
  return new Date(utcMillis);
}
