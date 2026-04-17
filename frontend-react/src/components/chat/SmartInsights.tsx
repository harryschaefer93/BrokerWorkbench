import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui';
import { TrendingUp, Lightbulb, AlertCircle, Clock } from 'lucide-react';
import { motion } from 'framer-motion';

interface Insight {
  id: string;
  title: string;
  description: string;
  icon: 'growth' | 'idea' | 'alert' | 'time';
  color: 'blue' | 'violet' | 'amber' | 'emerald';
}

const mockInsights: Insight[] = [
  {
    id: '1',
    title: 'Portfolio Growth',
    description: '12% increase opportunity identified',
    icon: 'growth',
    color: 'violet',
  },
  {
    id: '2',
    title: 'Renewal Alert',
    description: '5 policies expiring this week',
    icon: 'alert',
    color: 'amber',
  },
  {
    id: '3',
    title: 'Quote Efficiency',
    description: 'Avg response time improved 32%',
    icon: 'time',
    color: 'emerald',
  },
];

const iconMap = {
  growth: TrendingUp,
  idea: Lightbulb,
  alert: AlertCircle,
  time: Clock,
};

const colorMap = {
  blue: 'bg-blue-100 text-blue-600',
  violet: 'bg-violet-100 text-violet-600',
  amber: 'bg-amber-100 text-amber-600',
  emerald: 'bg-emerald-100 text-emerald-600',
};

export function SmartInsights() {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <Lightbulb className="h-4 w-4" />
          Smart Insights
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {mockInsights.map((insight, index) => {
          const Icon = iconMap[insight.icon];
          const colorClass = colorMap[insight.color];
          
          return (
            <motion.div
              key={insight.id}
              initial={{ opacity: 0, x: 10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.3, delay: index * 0.1 }}
              className="flex items-center gap-3 py-2 border-b last:border-0"
            >
              <div className={`p-2 rounded-full ${colorClass}`}>
                <Icon className="h-4 w-4" />
              </div>
              <div>
                <div className="font-medium text-sm">{insight.title}</div>
                <div className="text-xs text-muted-foreground">{insight.description}</div>
              </div>
            </motion.div>
          );
        })}
      </CardContent>
    </Card>
  );
}
