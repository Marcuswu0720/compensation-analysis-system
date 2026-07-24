import { Navigate, Route, Routes } from 'react-router-dom';
import { AppLayout } from './components/AppLayout';
import { ProtectedRoute } from './components/ProtectedRoute';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import ClockIn from './pages/ClockIn';
import MyAttendance from './pages/MyAttendance';
import LeaveApply from './pages/leave/Apply';
import MyApplications from './pages/leave/MyApplications';
import Approval from './pages/Approval';
import SpecialApproval from './pages/SpecialApproval';
import LocationCheckinReview from './pages/LocationCheckinReview';
import Schedule from './pages/Schedule';
import SpecialEvents from './pages/SpecialEvents';
import ReportsRegion from './pages/reports/Region';
import ReportsGlobal from './pages/reports/Global';
import Employees from './pages/admin/Employees';
import Teams from './pages/admin/Teams';
import Rules from './pages/admin/Rules';
import QcAnomalies from './pages/QcAnomalies';

function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/dashboard" element={<Dashboard />} />
        <Route
          path="/clock-in"
          element={
            <ProtectedRoute roles={['EMPLOYEE', 'LOCAL_MANAGER', 'LOCAL_HR']}>
              <ClockIn />
            </ProtectedRoute>
          }
        />
        <Route
          path="/my-attendance"
          element={
            <ProtectedRoute roles={['EMPLOYEE', 'LOCAL_MANAGER', 'LOCAL_HR']}>
              <MyAttendance />
            </ProtectedRoute>
          }
        />
        <Route
          path="/leave/apply"
          element={
            <ProtectedRoute roles={['EMPLOYEE', 'LOCAL_MANAGER', 'LOCAL_HR']}>
              <LeaveApply />
            </ProtectedRoute>
          }
        />
        <Route
          path="/leave/my-applications"
          element={
            <ProtectedRoute roles={['EMPLOYEE', 'LOCAL_MANAGER', 'LOCAL_HR']}>
              <MyApplications />
            </ProtectedRoute>
          }
        />
        <Route
          path="/approval"
          element={
            <ProtectedRoute roles={['LOCAL_HR']}>
              <Approval />
            </ProtectedRoute>
          }
        />
        <Route
          path="/special-approval"
          element={
            <ProtectedRoute roles={['HQ']}>
              <SpecialApproval />
            </ProtectedRoute>
          }
        />
        <Route
          path="/location-checkin/review"
          element={
            <ProtectedRoute roles={['LOCAL_MANAGER', 'LOCAL_HR']}>
              <LocationCheckinReview />
            </ProtectedRoute>
          }
        />
        <Route
          path="/schedule"
          element={
            <ProtectedRoute roles={['EMPLOYEE', 'LOCAL_MANAGER', 'LOCAL_HR']}>
              <Schedule />
            </ProtectedRoute>
          }
        />
        <Route
          path="/special-events"
          element={
            <ProtectedRoute roles={['LOCAL_HR']}>
              <SpecialEvents />
            </ProtectedRoute>
          }
        />
        <Route
          path="/reports/region"
          element={
            <ProtectedRoute roles={['LOCAL_MANAGER', 'LOCAL_HR']}>
              <ReportsRegion />
            </ProtectedRoute>
          }
        />
        <Route
          path="/reports/global"
          element={
            <ProtectedRoute roles={['HQ', 'LOCAL_HR']}>
              <ReportsGlobal />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/employees"
          element={
            <ProtectedRoute roles={['LOCAL_HR']}>
              <Employees />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/teams"
          element={
            <ProtectedRoute roles={['LOCAL_HR']}>
              <Teams />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/rules"
          element={
            <ProtectedRoute roles={['LOCAL_HR']}>
              <Rules />
            </ProtectedRoute>
          }
        />
        <Route
          path="/qc/anomalies"
          element={
            <ProtectedRoute roles={['QC_TEAM', 'HQ', 'LOCAL_HR']}>
              <QcAnomalies />
            </ProtectedRoute>
          }
        />
      </Route>
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}

export default App;
