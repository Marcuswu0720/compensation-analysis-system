import { useState } from 'react';
import { Button, Card, DatePicker, Form, Input, Modal, Select, Space, Table, Tabs, Typography, message } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { schedulesApi } from '../api/schedules';
import { teamsApi, usersApi } from '../api/org';
import { useAuthStore } from '../store/authStore';
import type { ScheduleAssignment } from '../api/types';

function AssignmentsTab() {
  const user = useAuthStore((s) => s.user);
  const isHr = user?.role === 'LOCAL_HR';
  const queryClient = useQueryClient();
  const [teamId, setTeamId] = useState<string>();
  const [range, setRange] = useState<[dayjs.Dayjs, dayjs.Dayjs]>([dayjs().startOf('week'), dayjs().endOf('week')]);
  const [changeTarget, setChangeTarget] = useState<ScheduleAssignment | null>(null);
  const [newShiftId, setNewShiftId] = useState<string>();
  const { data: teams = [] } = useQuery({ queryKey: ['teams'], queryFn: teamsApi.list, enabled: isHr || user?.role === 'LOCAL_MANAGER' });
  const { data = [] } = useQuery({
    queryKey: ['assignments', teamId, range[0].format('YYYY-MM-DD'), range[1].format('YYYY-MM-DD')],
    queryFn: () => schedulesApi.listAssignments({ teamId, from: range[0].format('YYYY-MM-DD'), to: range[1].format('YYYY-MM-DD') }),
  });
  // 调整班次时，班次候选需与目标员工当前班次所在团队一致
  const { data: shiftOptions = [] } = useQuery({
    queryKey: ['shifts', changeTarget?.shift.teamId],
    queryFn: () => schedulesApi.listShifts(changeTarget?.shift.teamId),
    enabled: !!changeTarget,
  });

  const changeMutation = useMutation({
    mutationFn: () => schedulesApi.changeAssignment(changeTarget!.id, newShiftId!),
    onSuccess: () => {
      message.success('排班已调整，变更记录已留痕');
      setChangeTarget(null);
      setNewShiftId(undefined);
      queryClient.invalidateQueries({ queryKey: ['assignments'] });
    },
    onError: (e: any) => message.error(e?.response?.data?.message ?? '调整失败'),
  });

  return (
    <div>
      <Space wrap style={{ marginBottom: 16 }}>
        {(isHr || user?.role === 'LOCAL_MANAGER') && (
          <Select style={{ width: 200 }} placeholder="选择团队" allowClear value={teamId} onChange={setTeamId} options={teams.map((t) => ({ value: t.id, label: t.name }))} />
        )}
        <DatePicker.RangePicker value={range} onChange={(v) => v && setRange(v as [dayjs.Dayjs, dayjs.Dayjs])} />
      </Space>
      <Table
        rowKey="id"
        scroll={{ x: "max-content" }}
        dataSource={data}
        columns={[
          { title: '员工', render: (_, r) => `${r.user.name}(${r.user.employeeNo})` },
          { title: '日期', dataIndex: 'date', render: (v) => dayjs(v).format('YYYY-MM-DD') },
          { title: '班次', render: (_, r) => `${r.shift.name} ${r.shift.startTime}-${r.shift.endTime}` },
          { title: '是否临时调整', dataIndex: 'isTemporary', render: (v) => (v ? '是' : '否') },
          ...(isHr
            ? [
                {
                  title: '操作',
                  render: (_: unknown, r: ScheduleAssignment) => (
                    <Button size="small" onClick={() => setChangeTarget(r)}>
                      调整班次
                    </Button>
                  ),
                },
              ]
            : []),
        ]}
      />
      <Modal
        title={changeTarget ? `调整 ${changeTarget.user.name} ${dayjs(changeTarget.date).format('YYYY-MM-DD')} 的班次` : ''}
        open={!!changeTarget}
        onCancel={() => setChangeTarget(null)}
        onOk={() => changeMutation.mutate()}
        confirmLoading={changeMutation.isPending}
        okButtonProps={{ disabled: !newShiftId }}
      >
        <Select
          style={{ width: '100%' }}
          placeholder="选择新班次"
          value={newShiftId}
          onChange={setNewShiftId}
          options={shiftOptions
            .filter((s) => s.id !== changeTarget?.shiftId)
            .map((s) => ({ value: s.id, label: `${s.name} ${s.startTime}-${s.endTime}` }))}
        />
      </Modal>
    </div>
  );
}

function ShiftsTab() {
  const queryClient = useQueryClient();
  const { data: teams = [] } = useQuery({ queryKey: ['teams'], queryFn: teamsApi.list });
  const [teamId, setTeamId] = useState<string>();
  const { data: shifts = [] } = useQuery({ queryKey: ['shifts', teamId], queryFn: () => schedulesApi.listShifts(teamId), enabled: !!teamId });

  const createMutation = useMutation({
    mutationFn: (values: any) => schedulesApi.createShift({ ...values, teamId }),
    onSuccess: () => {
      message.success('创建成功');
      queryClient.invalidateQueries({ queryKey: ['shifts', teamId] });
    },
  });

  return (
    <div>
      <Select style={{ width: 200, marginBottom: 16 }} placeholder="选择团队" value={teamId} onChange={setTeamId} options={teams.map((t) => ({ value: t.id, label: t.name }))} />
      {teamId && (
        <>
          <Table
            rowKey="id"
            scroll={{ x: "max-content" }}
            dataSource={shifts}
            style={{ marginBottom: 16 }}
            columns={[
              { title: '班次名称', dataIndex: 'name' },
              { title: '开始时间', dataIndex: 'startTime' },
              { title: '结束时间', dataIndex: 'endTime' },
            ]}
          />
          <Form layout="inline" onFinish={(v) => createMutation.mutate(v)}>
            <Form.Item name="name" rules={[{ required: true }]}>
              <Input placeholder="班次名称，如早班" />
            </Form.Item>
            <Form.Item name="startTime" rules={[{ required: true, pattern: /^([01]\d|2[0-3]):[0-5]\d$/, message: 'HH:mm' }]}>
              <Input placeholder="开始 HH:mm" />
            </Form.Item>
            <Form.Item name="endTime" rules={[{ required: true, pattern: /^([01]\d|2[0-3]):[0-5]\d$/, message: 'HH:mm' }]}>
              <Input placeholder="结束 HH:mm" />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={createMutation.isPending}>
              新增班次
            </Button>
          </Form>
        </>
      )}
    </div>
  );
}

function BatchGenerateTab() {
  const { data: teams = [] } = useQuery({ queryKey: ['teams'], queryFn: teamsApi.list });
  const [teamId, setTeamId] = useState<string>();
  const { data: shifts = [] } = useQuery({ queryKey: ['shifts', teamId], queryFn: () => schedulesApi.listShifts(teamId), enabled: !!teamId });
  const { data: users = [] } = useQuery({ queryKey: ['team-users', teamId], queryFn: () => usersApi.list({ teamId }), enabled: !!teamId });

  const mutation = useMutation({
    mutationFn: (values: any) =>
      schedulesApi.batchGenerate({
        userIds: values.userIds,
        shiftId: values.shiftId,
        dateFrom: values.range[0].format('YYYY-MM-DD'),
        dateTo: values.range[1].format('YYYY-MM-DD'),
      }),
    onSuccess: (res: any) => message.success(`生成完成：新增 ${res.createdCount} 条，跳过 ${res.skippedCount} 条（已有排班）`),
    onError: (e: any) => message.error(e?.response?.data?.message ?? '生成失败'),
  });

  return (
    <div style={{ maxWidth: 560 }}>
      <Form layout="vertical" onFinish={(v) => mutation.mutate(v)}>
        <Form.Item label="团队" required>
          <Select value={teamId} onChange={setTeamId} options={teams.map((t) => ({ value: t.id, label: t.name }))} />
        </Form.Item>
        <Form.Item name="shiftId" label="班次" rules={[{ required: true }]}>
          <Select options={shifts.map((s) => ({ value: s.id, label: `${s.name} ${s.startTime}-${s.endTime}` }))} disabled={!teamId} />
        </Form.Item>
        <Form.Item name="userIds" label="员工" rules={[{ required: true }]}>
          <Select mode="multiple" options={users.map((u) => ({ value: u.id, label: `${u.name}(${u.employeeNo})` }))} disabled={!teamId} />
        </Form.Item>
        <Form.Item name="range" label="排班周期" rules={[{ required: true }]}>
          <DatePicker.RangePicker style={{ width: '100%' }} />
        </Form.Item>
        <Button type="primary" htmlType="submit" loading={mutation.isPending}>
          批量生成排班
        </Button>
      </Form>
    </div>
  );
}

export default function Schedule() {
  const user = useAuthStore((s) => s.user);
  const isHr = user?.role === 'LOCAL_HR';

  return (
    <div>
      <Typography.Title level={3}>排班表</Typography.Title>
      <Card>
        <Tabs
          items={[
            { key: 'assignments', label: '排班表查看', children: <AssignmentsTab /> },
            ...(isHr
              ? [
                  { key: 'shifts', label: '班次管理', children: <ShiftsTab /> },
                  { key: 'batch', label: '批量生成排班', children: <BatchGenerateTab /> },
                ]
              : []),
          ]}
        />
      </Card>
    </div>
  );
}
