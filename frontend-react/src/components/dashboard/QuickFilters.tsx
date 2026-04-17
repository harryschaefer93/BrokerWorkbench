import { Button } from '@/components/ui';
import { Clock, DollarSign, AlertTriangle, Target } from 'lucide-react';
import { motion } from 'framer-motion';

const chips = [
  { label: 'Renewals Due', icon: Clock },
  { label: 'High Value Policies', icon: DollarSign },
  { label: 'Recent Claims', icon: AlertTriangle },
  { label: 'Cross-sell Opportunities', icon: Target },
];

interface QuickFiltersProps {
  onFilterClick?: (filter: string) => void;
  activeFilter?: string;
}

export function QuickFilters({ onFilterClick, activeFilter }: QuickFiltersProps) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {chips.map((chip, index) => {
        const Icon = chip.icon;
        const isActive = activeFilter === chip.label;
        
        return (
          <motion.div
            key={chip.label}
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2, delay: index * 0.05 }}
          >
            <Button
              variant={isActive ? 'default' : 'secondary'}
              size="sm"
              onClick={() => onFilterClick?.(chip.label)}
              className="gap-1.5"
            >
              <Icon className="h-3.5 w-3.5" />
              {chip.label}
            </Button>
          </motion.div>
        );
      })}
    </div>
  );
}
