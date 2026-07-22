import { useTranslation } from 'react-i18next';
import type { AttendanceStatus, ApprovalStatus, VerifyStatus, AttendanceMode, SpecialEventType, Role } from '../api/types';

export const STATUS_COLOR: Record<AttendanceStatus, string> = {
  NORMAL: 'green',
  LATE: 'orange',
  EARLY_LEAVE: 'orange',
  ABSENT: 'red',
  LEAVE: 'blue',
  FULL_ATTENDANCE: 'purple',
  PENDING: 'default',
  UNCONFIGURED: 'magenta',
};

export const APPROVAL_COLOR: Record<ApprovalStatus, string> = {
  PENDING: 'gold',
  APPROVED: 'green',
  REJECTED: 'red',
  CANCELLED: 'default',
};

export const VERIFY_COLOR: Record<VerifyStatus, string> = {
  PENDING: 'gold',
  APPROVED: 'green',
  REJECTED: 'red',
};

export function useStatusLabel(): Record<AttendanceStatus, string> {
  const { t } = useTranslation();
  return {
    NORMAL: t('status.NORMAL'),
    LATE: t('status.LATE'),
    EARLY_LEAVE: t('status.EARLY_LEAVE'),
    ABSENT: t('status.ABSENT'),
    LEAVE: t('status.LEAVE'),
    FULL_ATTENDANCE: t('status.FULL_ATTENDANCE'),
    PENDING: t('status.PENDING'),
    UNCONFIGURED: t('status.UNCONFIGURED'),
  };
}

export function useApprovalLabel(): Record<ApprovalStatus, string> {
  const { t } = useTranslation();
  return {
    PENDING: t('approvalStatus.PENDING'),
    APPROVED: t('approvalStatus.APPROVED'),
    REJECTED: t('approvalStatus.REJECTED'),
    CANCELLED: t('approvalStatus.CANCELLED'),
  };
}

export function useVerifyLabel(): Record<VerifyStatus, string> {
  const { t } = useTranslation();
  return {
    PENDING: t('verifyStatus.PENDING'),
    APPROVED: t('verifyStatus.APPROVED'),
    REJECTED: t('verifyStatus.REJECTED'),
  };
}

export function useModeLabel(): Record<AttendanceMode, string> {
  const { t } = useTranslation();
  return {
    OFFICE: t('mode.OFFICE'),
    SHIFT: t('mode.SHIFT'),
    LOCATION: t('mode.LOCATION'),
  };
}

export function useEventTypeLabel(): Record<SpecialEventType, string> {
  const { t } = useTranslation();
  return {
    EXTREME_WEATHER: t('eventType.EXTREME_WEATHER'),
    EMERGENCY_EVENT: t('eventType.EMERGENCY_EVENT'),
  };
}

export function useRoleLabel(): Record<Role, string> {
  const { t } = useTranslation();
  return {
    EMPLOYEE: t('roles.EMPLOYEE'),
    LOCAL_MANAGER: t('roles.LOCAL_MANAGER'),
    LOCAL_HR: t('roles.LOCAL_HR'),
    HQ: t('roles.HQ'),
  };
}

export function useLocalizedName(): (item: { name: string; nameEn?: string | null } | null | undefined) => string {
  const { i18n } = useTranslation();
  return (item) => {
    if (!item) return '';
    if (i18n.language === 'en' && item.nameEn) return item.nameEn;
    return item.name;
  };
}
