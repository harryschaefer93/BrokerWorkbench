import { motion } from 'framer-motion';
import { Card, CardContent, CardHeader, CardTitle, Button } from '@/components/ui';
import { Target, Home, Umbrella, Car } from 'lucide-react';
import { cn } from '@/lib/utils';

interface Opportunity {
  id: string;
  client_name: string;
  current_coverage: string;
  recommended: string;
  estimated_premium: string;
  reason: string;
  icon: 'home' | 'umbrella' | 'car';
  priority: 'high' | 'medium';
}

const mockOpportunities: Opportunity[] = [
  {
    id: '1',
    client_name: 'Smith Family',
    current_coverage: 'Auto policy holder',
    recommended: 'Home Insurance',
    estimated_premium: '$1,200-1,800',
    reason: 'No home insurance on file',
    icon: 'home',
    priority: 'high',
  },
  {
    id: '2',
    client_name: 'Johnson Family',
    current_coverage: 'Teen driver added',
    recommended: '$1M Umbrella',
    estimated_premium: '$285/year',
    reason: 'Increased liability risk',
    icon: 'umbrella',
    priority: 'medium',
  },
];

const iconMap = {
  home: Home,
  umbrella: Umbrella,
  car: Car,
};

interface OpportunityCardProps {
  opportunity: Opportunity;
  index: number;
}

function OpportunityCard({ opportunity, index }: OpportunityCardProps) {
  const Icon = iconMap[opportunity.icon];
  
  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.3, delay: index * 0.1 }}
      className={cn(
        "p-4 rounded-lg border-l-4",
        opportunity.priority === 'high' 
          ? "bg-violet-50 border-l-violet-500" 
          : "bg-amber-50 border-l-amber-500"
      )}
    >
      <div className="flex items-start gap-3">
        <div className={cn(
          "p-2 rounded-full",
          opportunity.priority === 'high' ? "bg-violet-100" : "bg-amber-100"
        )}>
          <Icon className={cn(
            "h-4 w-4",
            opportunity.priority === 'high' ? "text-violet-600" : "text-amber-600"
          )} />
        </div>
        
        <div className="flex-1">
          <div className="font-semibold text-sm">{opportunity.client_name}</div>
          <div className="text-xs text-muted-foreground mb-2">
            {opportunity.current_coverage} - {opportunity.reason}
          </div>
          <div className={cn(
            "text-sm font-medium",
            opportunity.priority === 'high' ? "text-violet-600" : "text-amber-600"
          )}>
            Estimated {opportunity.recommended}: {opportunity.estimated_premium}
          </div>
          <Button 
            size="sm" 
            variant={opportunity.priority === 'high' ? 'default' : 'secondary'}
            className="mt-2"
          >
            {opportunity.priority === 'high' ? 'Get Quote' : 'Schedule Review'}
          </Button>
        </div>
      </div>
    </motion.div>
  );
}

export function CrossSellOpportunities() {
  return (
    <Card className="h-full">
      <CardHeader className="pb-2">
        <CardTitle className="text-base flex items-center gap-2">
          <Target className="h-4 w-4" />
          Cross-Sell Opportunities
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {mockOpportunities.map((opportunity, index) => (
            <OpportunityCard 
              key={opportunity.id} 
              opportunity={opportunity} 
              index={index} 
            />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
