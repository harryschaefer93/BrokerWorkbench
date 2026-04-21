import { motion } from 'framer-motion';
import { Card, CardContent } from '@/components/ui';
import { useRenewalDashboard, useDashboardMetrics, useCarriers } from '@/hooks';
import { 
  DollarSign, 
  FileText, 
  Building2, 
  Users, 
  AlertCircle
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Task } from '@/types';

const priorityConfig = {
  high: { color: 'bg-red-500', icon: '🔴', label: 'High' },
  medium: { color: 'bg-amber-500', icon: '🟡', label: 'Medium' },
  low: { color: 'bg-emerald-500', icon: '🟢', label: 'Low' },
} as const;

// Animated metric card
interface MetricCardProps {
  label: string;
  value: string | number;
  icon: React.ReactNode;
  loading?: boolean;
}

function MetricCard({ label, value, icon, loading }: MetricCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <Card className="bg-primary text-primary-foreground">
        <CardContent className="p-4">
          <div className="flex items-center justify-between mb-2">
            {icon}
          </div>
          <div className="text-2xl font-bold mb-1">
            {loading ? (
              <span className="animate-pulse">--</span>
            ) : (
              value
            )}
          </div>
          <div className="text-xs opacity-80">{label}</div>
        </CardContent>
      </Card>
    </motion.div>
  );
}

// Task item component
interface TaskItemProps {
  task: Task;
  index: number;
}

function TaskItem({ task, index }: TaskItemProps) {
  const config = priorityConfig[task.priority];
  
  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.3, delay: index * 0.1 }}
      whileHover={{ x: 5 }}
      className={cn(
        "p-3 rounded-lg cursor-pointer transition-colors hover:bg-muted/50",
        "border-l-4",
        task.priority === 'high' && "border-l-red-500",
        task.priority === 'medium' && "border-l-amber-500",
        task.priority === 'low' && "border-l-emerald-500",
      )}
    >
      <div className="flex items-start gap-3">
        <span className="text-sm mt-0.5">{config.icon}</span>
        <div className="flex-1 min-w-0">
          <div className="font-medium text-sm truncate">{task.title}</div>
          <div className="text-xs text-muted-foreground truncate">{task.description}</div>
        </div>
      </div>
    </motion.div>
  );
}

// Carrier status item
interface CarrierStatusProps {
  name: string;
  status: 'online' | 'offline' | 'degraded';
  initials: string;
}

function CarrierStatus({ name, status, initials }: CarrierStatusProps) {
  const statusConfig = {
    online: { color: 'bg-emerald-500', label: 'Online' },
    offline: { color: 'bg-red-500', label: 'Offline' },
    degraded: { color: 'bg-amber-500', label: 'Degraded' },
  };
  
  const config = statusConfig[status];
  
  return (
    <div className="flex items-center justify-between py-2">
      <div className="flex items-center gap-2">
        <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center text-xs font-medium">
          {initials}
        </div>
        <span className="text-sm">{name}</span>
      </div>
      <div className="flex items-center gap-2">
        <div className={cn("h-2 w-2 rounded-full", config.color)} />
        <span className="text-xs text-muted-foreground">{config.label}</span>
      </div>
    </div>
  );
}

export function Sidebar() {
  const { metrics, loading: metricsLoading } = useDashboardMetrics();
  const { data: renewals } = useRenewalDashboard();
  const { data: carriers } = useCarriers();

  // Convert renewals to tasks
  const tasks: Task[] = [
    ...(renewals?.critical?.slice(0, 2).map((r, i) => ({
      id: `critical-${i}`,
      title: `${r.client_name} - ${r.policy_type} Renewal`,
      description: `Due in ${r.days_until_expiry} days - $${r.premium.toLocaleString()} premium`,
      priority: 'high' as const,
      client_name: r.client_name,
      premium: r.premium,
    })) || []),
    ...(renewals?.high?.slice(0, 1).map((r, i) => ({
      id: `high-${i}`,
      title: `Follow up: ${r.client_name}`,
      description: `${r.policy_type} quote requested`,
      priority: 'medium' as const,
      client_name: r.client_name,
    })) || []),
    ...(renewals?.medium?.slice(0, 1).map((r, i) => ({
      id: `medium-${i}`,
      title: `${r.client_name} Annual Review`,
      description: 'Scheduled for next week',
      priority: 'low' as const,
      client_name: r.client_name,
    })) || []),
  ];

  // Map carriers to status items
  const carrierStatuses: CarrierStatusProps[] = carriers.slice(0, 5).map(c => ({
    name: c.name,
    initials: c.name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase(),
    status: c.api_status === 'active' ? 'online' : 'offline',
  }));

  const formatCurrency = (value: number) => {
    if (value >= 1000000) return `$${(value / 1000000).toFixed(1)}M`;
    if (value >= 1000) return `$${(value / 1000).toFixed(0)}K`;
    return `$${value}`;
  };

  return (
    <aside className="w-72 border-r bg-card overflow-y-auto h-[calc(100vh-4rem)]">
      <div className="p-4 space-y-4">
        {/* Priority Tasks */}
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-4">
              <AlertCircle className="h-4 w-4 text-muted-foreground" />
              <h3 className="font-semibold text-sm">Priority Tasks</h3>
            </div>
            <div className="space-y-2">
              {tasks.length > 0 ? (
                tasks.map((task, i) => (
                  <TaskItem key={task.id} task={task} index={i} />
                ))
              ) : (
                <div className="text-sm text-muted-foreground italic py-2">
                  No urgent tasks
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Quick Stats */}
        <div className="grid grid-cols-2 gap-3">
          <MetricCard 
            label="Premium at Risk"
            value={formatCurrency(metrics.totalPremiumAtRisk)}
            icon={<DollarSign className="h-4 w-4 opacity-70" />}
            loading={metricsLoading}
          />
          <MetricCard 
            label="In Renewal"
            value={metrics.policiesInRenewal}
            icon={<FileText className="h-4 w-4 opacity-70" />}
            loading={metricsLoading}
          />
          <MetricCard 
            label="Active Carriers"
            value={metrics.activeCarriers}
            icon={<Building2 className="h-4 w-4 opacity-70" />}
            loading={metricsLoading}
          />
          <MetricCard 
            label="Total Clients"
            value={metrics.totalClients}
            icon={<Users className="h-4 w-4 opacity-70" />}
            loading={metricsLoading}
          />
        </div>

        {/* Carrier Status */}
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-3">
              <Building2 className="h-4 w-4 text-muted-foreground" />
              <h3 className="font-semibold text-sm">Carrier Connectivity</h3>
            </div>
            <div className="space-y-1">
              {carrierStatuses.length > 0 ? (
                carrierStatuses.map((carrier) => (
                  <CarrierStatus key={carrier.name} {...carrier} />
                ))
              ) : (
                <div className="text-sm text-muted-foreground italic py-2">
                  Loading carriers...
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Foundry Branding */}
      <div className="p-4 border-t">
        <a href="https://ai.azure.com" target="_blank" rel="noopener noreferrer"
           className="flex items-center gap-2 text-xs text-muted-foreground hover:text-violet-500 transition-colors group">
          <svg className="h-4 w-4 text-violet-500 group-hover:text-violet-600 transition-colors" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z" fill="currentColor"/>
          </svg>
          <div>
            <div className="font-medium text-foreground/80">Microsoft Foundry</div>
            <div className="text-[10px] opacity-70">AI agents & intelligence</div>
          </div>
        </a>
      </div>
    </aside>
  );
}
