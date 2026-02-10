import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';
import {
    ChatBubbleLeftRightIcon,
    DocumentTextIcon,
    ArrowRightOnRectangleIcon,
    Bars3Icon,
    ShieldCheckIcon,
    SparklesIcon
} from '@heroicons/react/24/outline';
import { useState, useEffect } from 'react';
import { healthService } from '@/services';
import clsx from 'clsx';

export function Layout() {
    const { isAuthenticated, user, logout } = useAuthStore();
    const navigate = useNavigate();
    const [isSidebarOpen, setIsSidebarOpen] = useState(false);
    const [healthStatus, setHealthStatus] = useState<'healthy' | 'unhealthy' | 'loading'>('loading');

    useEffect(() => {
        // Check health on mount
        healthService.check()
            .then(() => setHealthStatus('healthy'))
            .catch(() => setHealthStatus('unhealthy'));
    }, []);

    const handleLogout = () => {
        logout();
        navigate('/login');
    };

    const navItems = [
        { to: '/', icon: ChatBubbleLeftRightIcon, label: 'Chat' },
        { to: '/documents', icon: DocumentTextIcon, label: 'Documents' },
    ];

    return (
        <div className="flex h-screen bg-dark-950">
            {/* Mobile sidebar backdrop */}
            {isSidebarOpen && (
                <div
                    className="fixed inset-0 bg-black/50 z-40 lg:hidden"
                    onClick={() => setIsSidebarOpen(false)}
                />
            )}

            {/* Sidebar */}
            <aside className={clsx(
                "fixed lg:static inset-y-0 left-0 z-50 w-64 glass flex flex-col transform transition-transform duration-300 ease-in-out",
                isSidebarOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
            )}>
                {/* Logo */}
                <div className="p-6 border-b border-dark-700">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-nvidia to-primary-500 flex items-center justify-center">
                            <svg className="w-6 h-6 text-white" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
                            </svg>
                        </div>
                        <div>
                            <div className="flex items-center gap-2">
                                <h1 className="text-lg font-bold text-white leading-none">RAG PRO</h1>
                                <span className="px-1.5 py-0.5 rounded bg-nvidia text-[8px] font-black text-white uppercase tracking-tighter">
                                    Enterprise
                                </span>
                            </div>
                            <p className="text-[10px] text-dark-400 mt-1 uppercase tracking-widest font-semibold italic">NVIDIA NIM CORE</p>
                        </div>
                    </div>
                </div>

                {/* Navigation */}
                <nav className="flex-1 p-4 space-y-2">
                    {navItems.map((item) => (
                        <NavLink
                            key={item.to}
                            to={item.to}
                            onClick={() => setIsSidebarOpen(false)}
                            className={({ isActive }: { isActive: boolean }) => clsx(
                                "flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-200",
                                isActive
                                    ? "bg-nvidia/20 text-nvidia border border-nvidia/30"
                                    : "text-dark-300 hover:bg-dark-800 hover:text-white"
                            )}
                        >
                            <item.icon className="w-5 h-5" />
                            <span className="font-medium">{item.label}</span>
                        </NavLink>
                    ))}
                </nav>

                {/* Status & User */}
                <div className="p-4 border-t border-dark-700 space-y-4">
                    {/* Health Status */}
                    <div className="flex items-center gap-2 px-4 py-2 rounded-lg bg-dark-800">
                        <div className={clsx(
                            "w-2 h-2 rounded-full",
                            healthStatus === 'healthy' && "bg-green-500 animate-pulse",
                            healthStatus === 'unhealthy' && "bg-red-500",
                            healthStatus === 'loading' && "bg-yellow-500 animate-pulse"
                        )} />
                        <span className="text-sm text-dark-400">
                            {healthStatus === 'healthy' && 'System Online'}
                            {healthStatus === 'unhealthy' && 'System Offline'}
                            {healthStatus === 'loading' && 'Checking...'}
                        </span>
                    </div>

                    {/* Capabilities */}
                    <div className="px-4 py-3 rounded-lg bg-nvidia/5 border border-nvidia/10 space-y-2">
                        <div className="flex items-center justify-between">
                            <span className="text-[10px] font-bold text-dark-400 uppercase tracking-wider">Capabilities</span>
                        </div>
                        <div className="flex items-center gap-2">
                            <ShieldCheckIcon className="w-3.5 h-3.5 text-nvidia" />
                            <span className="text-xs text-dark-200">Guardrails Active</span>
                        </div>
                        <div className="flex items-center gap-2">
                            <SparklesIcon className="w-3.5 h-3.5 text-nvidia" />
                            <span className="text-xs text-dark-200">Multimodal RAG</span>
                        </div>
                    </div>

                    {/* User Info */}
                    {isAuthenticated && user && (
                        <div className="flex items-center justify-between px-4 py-3 rounded-lg bg-dark-800">
                            <div className="flex items-center gap-3">
                                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-nvidia to-primary-500 flex items-center justify-center text-white font-bold text-sm">
                                    {user.username.charAt(0).toUpperCase()}
                                </div>
                                <div>
                                    <p className="text-sm font-medium text-white">{user.username}</p>
                                    <p className="text-xs text-dark-400">{user.email}</p>
                                </div>
                            </div>
                            <button
                                onClick={handleLogout}
                                className="p-2 text-dark-400 hover:text-red-400 transition-colors"
                                title="Logout"
                            >
                                <ArrowRightOnRectangleIcon className="w-5 h-5" />
                            </button>
                        </div>
                    )}
                </div>
            </aside>

            {/* Main Content */}
            <main className="flex-1 flex flex-col min-w-0">
                {/* Mobile Header */}
                <header className="lg:hidden flex items-center justify-between p-4 border-b border-dark-700 glass">
                    <button
                        onClick={() => setIsSidebarOpen(true)}
                        className="p-2 text-dark-300 hover:text-white"
                    >
                        <Bars3Icon className="w-6 h-6" />
                    </button>
                    <h1 className="text-lg font-bold gradient-text">RAG Assistant</h1>
                    <div className="w-10" /> {/* Spacer */}
                </header>

                {/* Page Content */}
                <div className="flex-1 overflow-hidden">
                    <Outlet />
                </div>
            </main>
        </div>
    );
}
