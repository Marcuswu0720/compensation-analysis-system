import { SetMetadata } from '@nestjs/common';

// 总部账号默认对所有写接口（非 GET）强制拒绝（见需求文档 2.2 节的强约束）。
// 极少数与"是否总部"无关的自服务接口（如登出、修改自己的密码）可用此装饰器放行。
export const ALLOW_HQ_WRITE_KEY = 'allowHqWrite';
export const AllowHqWrite = () => SetMetadata(ALLOW_HQ_WRITE_KEY, true);
