import { Controller, Get, Query } from '@nestjs/common';
import { spawn } from 'child_process';
import { AppService } from './app.service';
import { Public } from './common/decorators/public.decorator';
import { PrismaService } from './prisma/prisma.service';

// 临时端点：免费版Render没有Shell权限，换数据库后手动跑一次seed用，验证完会在下一次提交里删掉
const SEED_ONCE_KEY = 'a9aab7cdc9f38f15e1f50459067ddc42';

let seedState: { status: 'idle' | 'running' | 'done' | 'error'; output: string } = { status: 'idle', output: '' };

@Controller()
export class AppController {
  constructor(
    private readonly appService: AppService,
    private readonly prisma: PrismaService,
  ) {}

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
  seedOnce(@Query('key') key?: string) {
    if (key !== SEED_ONCE_KEY) {
      return { ok: false, message: 'invalid key' };
    }
    if (seedState.status === 'running') {
      return { ok: true, message: 'already running, check /api/_seed-status' };
    }
    seedState = { status: 'running', output: '' };
    // 后台跑，立刻返回响应，避免请求方一直挂着等待导致前端误以为卡死
    const child = spawn('node_modules/.bin/ts-node', ['prisma/seed.ts'], { cwd: process.cwd() });
    child.stdout.on('data', (d) => (seedState.output += d.toString()));
    child.stderr.on('data', (d) => (seedState.output += d.toString()));
    child.on('close', (code) => {
      seedState.status = code === 0 ? 'done' : 'error';
      seedState.output += `\n[exit code ${code}]`;
    });
    child.on('error', (e) => {
      seedState.status = 'error';
      seedState.output += `\n[spawn error] ${e.message}`;
    });
    return { ok: true, message: 'started, check /api/_seed-status?key=... in ~30s' };
  }

  @Public()
  @Get('_seed-status')
  async seedStatus(@Query('key') key?: string) {
    if (key !== SEED_ONCE_KEY) {
      return { ok: false, message: 'invalid key' };
    }
    const userCount = await this.prisma.user.count().catch((e) => `error: ${e.message}`);
    return { ...seedState, userCount };
  }
}
