import { Search, Bell } from 'lucide-react';
import { Input, Avatar } from '@/components/ui';
import { useConnectionStatus } from '@/hooks';
import { cn } from '@/lib/utils';

interface HeaderProps {
  urgentCount?: number;
}

export function Header({ urgentCount = 0 }: HeaderProps) {
  const { isConnected, checking } = useConnectionStatus();

  return (
    <header className="h-16 border-b bg-card px-6 flex items-center justify-between gap-4 sticky top-0 z-50">
      {/* Logo Section */}
      <div className="flex items-center gap-4">
        <div className="bg-primary text-primary-foreground px-4 py-2 rounded-md font-semibold text-sm">
          BrokerHub
        </div>
        
        {/* Connection Status */}
        <div className="flex items-center gap-2 text-sm">
          <div 
            className={cn(
              "h-2 w-2 rounded-full",
              checking ? "bg-muted-foreground animate-pulse" :
              isConnected ? "bg-emerald-500 animate-pulse-ring" : "bg-destructive"
            )} 
          />
          <span className={cn(
            "text-xs",
            isConnected ? "text-emerald-600" : "text-muted-foreground"
          )}>
            {checking ? 'Connecting...' : isConnected ? 'Live' : 'Offline'}
          </span>
        </div>
      </div>

      {/* Search Bar */}
      <div className="flex-1 max-w-md mx-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input 
            type="text"
            placeholder="Search policies, clients, carriers... (AI-powered)"
            className="pl-10 bg-muted/50"
          />
        </div>
      </div>

      {/* User Section */}
      <div className="flex items-center gap-4">
        {/* Notifications */}
        <div className="relative">
          <button className="relative p-2 hover:bg-muted rounded-md transition-colors">
            <Bell className="h-5 w-5 text-muted-foreground" />
            {urgentCount > 0 && (
              <span className="absolute -top-1 -right-1 bg-destructive text-destructive-foreground text-xs rounded-full h-5 min-w-5 flex items-center justify-center px-1 font-medium">
                {urgentCount}
              </span>
            )}
          </button>
        </div>

        {/* User Avatar */}
        <div className="flex items-center gap-3">
          <Avatar fallback="JB" size="md" />
          <span className="text-sm font-medium hidden md:block">John Broker</span>
        </div>
      </div>
    </header>
  );
}
