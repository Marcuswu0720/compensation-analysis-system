import { Controller, Get, Query } from '@nestjs/common';
import { exec } from 'child_process';
import { promisify } from 'util';
import { AppService } from './app.service';
import { Public } from './common/decorators/public.decorator';

const execAsync = promisify(exec);

// 临时端点：免费版Render没有Shell权限，换数据库后手动跑一次seed用，验证完会在下一次提交里删掉
const SEED_ONCE_KEY = 'a9aab7cdc9f38f15e1f50459067ddc42';

@Controller()
export class AppController {
  constructor(private readonly appService: AppService) {}

  @Public()
  @Get()
  getHello(): string {
    return this.appService.getHello();
  }

  @Public()
  @Get('health')
  health() {
    return { status: 'ok', timestamp: new Date().toISOString() };
  }

  @Public()
  @Get('_seed-once')
  async seedOnce(@Query('key') key?: string) {
    if (key !== SEED_ONCE_KEY) {
      return { ok: false, message: 'invalid key' };
    }
    try {
      const { stdout, stderr } = await execAsync('npx prisma db seed', { cwd: process.cwd(), timeout: 60000 });
      return { ok: true, stdout, stderr };
    } catch (e: any) {
      return { ok: false, error: e.message, stdout: e.stdout, stderr: e.stderr };
    }
  }
}
