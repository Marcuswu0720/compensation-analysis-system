import { Button, Card, Form, Input, Typography, message } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { authApi } from '../api/auth';
import { useAuthStore } from '../store/authStore';

export default function Login() {
  const navigate = useNavigate();
  const setAuth = useAuthStore((s) => s.setAuth);

  const mutation = useMutation({
    mutationFn: (values: { email: string; password: string }) => authApi.login(values.email, values.password),
    onSuccess: (data) => {
      setAuth(data.user, data.accessToken, data.refreshToken);
      navigate('/dashboard');
    },
    onError: () => {
      message.error('登录失败，请检查邮箱和密码');
    },
  });

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: '#f0f2f5', padding: 16 }}>
      <Card style={{ width: '100%', maxWidth: 380 }}>
        <Typography.Title level={3} style={{ textAlign: 'center' }}>
          企业考勤管理系统
        </Typography.Title>
        <Form layout="vertical" onFinish={(values) => mutation.mutate(values)}>
          <Form.Item name="email" label="邮箱" rules={[{ required: true, message: '请输入邮箱' }]}>
            <Input placeholder="you@example.com" />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password placeholder="密码" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block loading={mutation.isPending}>
              登录
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
}
