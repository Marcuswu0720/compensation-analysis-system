import { useState } from 'react';
import { Button, Card, DatePicker, Form, Input, Modal, Select, Space, Table, Tabs, Typography, message } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import { schedulesApi } from '../api/schedules';
import { teamsApi, usersApi } from '../api/org';
import { useAuthStore } from '../store/authStore';
import type { ScheduleAssignment } from '../api/types';

function AssignmentsTab() {
  const { t } = useTranslation();
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
      message.success(t('schedule.changeSuccess'));
      setChangeTarget(null);
      setNewShiftId(undefined);
      queryClient.invalidateQueries({ queryKey: ['assignments'] });
    },
    onError: (e: any) => message.error(e?.response?.data?.message ?? t('schedule.changeFailed')),
  });

  return (
    <div>
      <Space wrap style={{ marginBottom: 16 }}>
        {(isHr || user?.role === 'LOCAL_MANAGER') && (
          <Select style={{ width: 200 }} placeholder={t('common.selectTeam')} allowClear value={teamId} onChange={setTeamId} options={teams.map((tm) => ({ value: tm.id, label: tm.name }))} />
        )}
        <DatePicker.RangePicker value={range} onChange={(v) => v && setRange(v as [dayjs.Dayjs, dayjs.Dayjs])} />
      </Space>
      <Table
        rowKey="id"
        scroll={{ x: "max-content" }}
        dataSource={data}
        columns={[
          { title: t('common.employee'), render: (_, r) => `${r.user.name}(${r.user.employeeNo})` },
          { title: t('common.date'), dataIndex: 'date', render: (v) => dayjs(v).format('YYYY-MM-DD') },
          { title: t('schedule.shift'), render: (_, r) => `${r.shift.name} ${r.shift.startTime}-${r.shift.endTime}` },
          { title: t('schedule.isTemporary'), dataIndex: 'isTemporary', render: (v) => (v ? t('common.yes') : t('common.no')) },
          ...(isHr
            ? [
                {
                  title: t('common.actions'),
                  render: (_: unknown, r: ScheduleAssignment) => (
                    <Button size="small" onClick={() => setChangeTarget(r)}>
                      {t('schedule.changeShift')}
                    </Button>
                  ),
                },
              ]
            : []),
        ]}
      />
      <Modal
        title={changeTarget ? t('schedule.changeShiftTitle', { name: changeTarget.user.name, date: dayjs(changeTarget.date).format('YYYY-MM-DD') }) : ''}
        open={!!changeTarget}
        onCancel={() => setChangeTarget(null)}
        onOk={() => changeMutation.mutate()}
        confirmLoading={changeMutation.isPending}
        okButtonProps={{ disabled: !newShiftId }}
      >
        <Select
          style={{ width: '100%' }}
          placeholder={t('schedule.selectNewShift')}
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
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { data: teams = [] } = useQuery({ queryKey: ['teams'], queryFn: teamsApi.list });
  const [teamId, setTeamId] = useState<string>();
  const { data: shifts = [] } = useQuery({ queryKey: ['shifts', teamId], queryFn: () => schedulesApi.listShifts(teamId), enabled: !!teamId });

  const createMutation = useMutation({
    mutationFn: (values: any) => schedulesApi.createShift({ ...values, teamId }),
    onSuccess: () => {
      message.success(t('schedule.createSuccess'));
      queryClient.invalidateQueries({ queryKey: ['shifts', teamId] });
    },
  });

  return (
    <div>
      <Select style={{ width: 200, marginBottom: 16 }} placeholder={t('common.selectTeam')} value={teamId} onChange={setTeamId} options={teams.map((tm) => ({ value: tm.id, label: tm.name }))} />
      {teamId && (
        <>
          <Table
            rowKey="id"
            scroll={{ x: "max-content" }}
            dataSource={shifts}
            style={{ marginBottom: 16 }}
            columns={[
              { title: t('schedule.shiftName'), dataIndex: 'name' },
              { title: t('schedule.startTime'), dataIndex: 'startTime' },
              { title: t('schedule.endTime'), dataIndex: 'endTime' },
            ]}
          />
          <Form layout="inline" onFinish={(v) => createMutation.mutate(v)}>
            <Form.Item name="name" rules={[{ required: true }]}>
              <Input placeholder={t('schedule.shiftNamePlaceholder')} />
            </Form.Item>
            <Form.Item name="startTime" rules={[{ required: true, pattern: /^([01]\d|2[0-3]):[0-5]\d$/, message: 'HH:mm' }]}>
              <Input placeholder={t('schedule.startTimePlaceholder')} />
            </Form.Item>
            <Form.Item name="endTime" rules={[{ required: true, pattern: /^([01]\d|2[0-3]):[0-5]\d$/, message: 'HH:mm' }]}>
              <Input placeholder={t('schedule.endTimePlaceholder')} />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={createMutation.isPending}>
              {t('schedule.addShift')}
            </Button>
          </Form>
        </>
      )}
    </div>
  );
}

function BatchGenerateTab() {
  const { t } = useTranslation();
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
    onSuccess: (res: any) => message.success(t('schedule.batchDone', { created: res.createdCount, skipped: res.skippedCount })),
    onError: (e: any) => message.error(e?.response?.data?.message ?? t('schedule.batchFailed')),
  });

  return (
    <div style={{ maxWidth: 560 }}>
      <Form layout="vertical" onFinish={(v) => mutation.mutate(v)}>
        <Form.Item label={t('schedule.batchTeam')} required>
          <Select value={teamId} onChange={setTeamId} options={teams.map((tm) => ({ value: tm.id, label: tm.name }))} />
        </Form.Item>
        <Form.Item name="shiftId" label={t('schedule.batchShift')} rules={[{ required: true }]}>
          <Select options={shifts.map((s) => ({ value: s.id, label: `${s.name} ${s.startTime}-${s.endTime}` }))} disabled={!teamId} />
        </Form.Item>
        <Form.Item name="userIds" label={t('schedule.batchEmployees')} rules={[{ required: true }]}>
          <Select mode="multiple" options={users.map((u) => ({ value: u.id, label: `${u.name}(${u.employeeNo})` }))} disabled={!teamId} />
        </Form.Item>
        <Form.Item name="range" label={t('schedule.batchPeriod')} rules={[{ required: true }]}>
          <DatePicker.RangePicker style={{ width: '100%' }} />
        </Form.Item>
        <Button type="primary" htmlType="submit" loading={mutation.isPending}>
          {t('schedule.batchGenerate')}
        </Button>
      </Form>
    </div>
  );
}

export default function Schedule() {
  const { t } = useTranslation();
  const user = useAuthStore((s) => s.user);
  const isHr = user?.role === 'LOCAL_HR';

  return (
    <div>
      <Typography.Title level={3}>{t('schedule.title')}</Typography.Title>
      <Card>
        <Tabs
          items={[
            { key: 'assignments', label: t('schedule.assignmentsTab'), children: <AssignmentsTab /> },
            ...(isHr
              ? [
                  { key: 'shifts', label: t('schedule.shiftsTab'), children: <ShiftsTab /> },
                  { key: 'batch', label: t('schedule.batchTab'), children: <BatchGenerateTab /> },
                ]
              : []),
          ]}
        />
      </Card>
    </div>
  );
}
