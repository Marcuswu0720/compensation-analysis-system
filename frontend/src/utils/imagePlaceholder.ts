// 定位打卡照片在 DB 存储上线之前拍摄的历史记录，其原始文件曾保存在旧的本地磁盘目录，
// 迁移到数据库存储后无法找回；用该占位图代替浏览器默认的裂图图标。
export const PHOTO_FALLBACK =
  'data:image/svg+xml;utf8,' +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="200" height="150" viewBox="0 0 200 150">
      <rect width="200" height="150" fill="#f5f5f5"/>
      <g fill="none" stroke="#bfbfbf" stroke-width="2">
        <rect x="20" y="20" width="160" height="110" rx="4"/>
        <circle cx="60" cy="55" r="10"/>
        <path d="M20 110 L70 70 L110 100 L140 75 L180 110" />
      </g>
    </svg>`,
  );
