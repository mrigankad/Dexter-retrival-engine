import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';
import { authService } from '@/services';
import {
    KeyIcon,
    UserIcon,
    ArrowRightIcon,
    SparklesIcon,
    ShieldCheckIcon,
    ArrowPathIcon
} from '@heroicons/react/24/outline';
import toast from 'react-hot-toast';
import { motion } from 'framer-motion';

export function LoginPage() {
    const [username, setUsername] = useState('admin');
    const [password, setPassword] = useState('admin123');
    const [isLoading, setIsLoading] = useState(false);
    const [isRegistering, setIsRegistering] = useState(false);
    const [email, setEmail] = useState('');

    const navigate = useNavigate();
    const login = useAuthStore((state) => state.login);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setIsLoading(true);

        try {
            if (isRegistering) {
                await authService.register({ username, email, password });
                toast.success('Registration successful! Please login.');
                setIsRegistering(false);
            } else {
                const tokens = await authService.login({ username, password });
                // In a real app, we'd fetch the user's profile info here
                login(tokens.access_token, {
                    id: '1',
                    username,
                    email: email || `${username}@example.com`
                });
                toast.success(`Welcome back, ${username}!`);
                navigate('/');
            }
        } catch (error) {
            const axiosError = error as { response?: { data?: { detail?: string } } };
            const message = axiosError.response?.data?.detail || 'Authentication failed';
            toast.error(message);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="min-h-screen flex flex-col lg:flex-row bg-dark-950 overflow-hidden">
            {/* Left Side: Illustration & Branding */}
            <div className="hidden lg:flex lg:w-1/2 relative bg-dark-900 items-center justify-center p-12 overflow-hidden">
                {/* Animated background elements */}
                <div className="absolute top-0 right-0 -translate-y-1/2 translate-x-1/2 w-[600px] h-[600px] bg-nvidia/10 rounded-full blur-[120px]" />
                <div className="absolute bottom-0 left-0 translate-y-1/2 -translate-x-1/2 w-[400px] h-[400px] bg-primary-900/20 rounded-full blur-[100px]" />

                <div className="relative z-10 max-w-lg text-center">
                    <motion.div
                        initial={{ scale: 0.8, opacity: 0 }}
                        animate={{ scale: 1, opacity: 1 }}
                        transition={{ duration: 0.5 }}
                        className="w-24 h-24 rounded-3xl bg-gradient-to-br from-nvidia to-primary-600 flex items-center justify-center mx-auto mb-8 shadow-2xl shadow-nvidia/20"
                    >
                        <SparklesIcon className="w-12 h-12 text-white" />
                    </motion.div>

                    <motion.h1
                        initial={{ y: 20, opacity: 0 }}
                        animate={{ y: 0, opacity: 1 }}
                        transition={{ delay: 0.2 }}
                        className="text-4xl font-bold text-white mb-6"
                    >
                        NVIDIA NIM Powered <br />
                        <span className="gradient-text">Bodham</span>
                    </motion.h1>

                    <motion.p
                        initial={{ y: 20, opacity: 0 }}
                        animate={{ y: 0, opacity: 1 }}
                        transition={{ delay: 0.3 }}
                        className="text-dark-400 text-lg leading-relaxed"
                    >
                        Experience lightning-fast document intelligence with NVIDIA NIM microservices.
                        Upload, index, and chat with your knowledge base in seconds.
                    </motion.p>

                    <motion.div
                        initial={{ y: 20, opacity: 0 }}
                        animate={{ y: 0, opacity: 1 }}
                        transition={{ delay: 0.4 }}
                        className="mt-12 grid grid-cols-3 gap-6"
                    >
                        {[
                            { label: 'PDF Parsing', icon: '📄' },
                            { label: 'Vector Search', icon: '🔍' },
                            { label: 'NVIDIA LLMs', icon: '🚀' }
                        ].map((item) => (
                            <div key={item.label} className="p-4 rounded-2xl glass bg-dark-800/50">
                                <div className="text-2xl mb-1">{item.icon}</div>
                                <div className="text-xs font-semibold text-dark-300 uppercase tracking-wider">{item.label}</div>
                            </div>
                        ))}
                    </motion.div>
                </div>
            </div>

            {/* Right Side: Form */}
            <div className="flex-1 flex items-center justify-center p-8 relative">
                {/* Mobile background elements */}
                <div className="lg:hidden absolute top-0 left-1/2 -translate-x-1/2 w-full h-1/2 bg-nvidia/5 rounded-full blur-[80px]" />

                <div className="w-full max-w-md relative z-10">
                    <div className="text-center mb-10">
                        <h2 className="text-3xl font-bold text-white mb-2">
                            {isRegistering ? 'Create Account' : 'Welcome Back'}
                        </h2>
                        <p className="text-dark-500">
                            {isRegistering
                                ? 'Join us to start processing your documents'
                                : 'Sign in to access your RAG workspace'
                            }
                        </p>
                    </div>

                    <form onSubmit={handleSubmit} className="space-y-6">
                        <div className="space-y-4">
                            {/* Username */}
                            <div className="space-y-2">
                                <label className="text-sm font-medium text-dark-300 ml-1">Username</label>
                                <div className="relative">
                                    <UserIcon className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-dark-500" />
                                    <input
                                        type="text"
                                        value={username}
                                        onChange={(e) => setUsername(e.target.value)}
                                        placeholder="Enter your username"
                                        required
                                        className="w-full pl-12 pr-4 py-3.5 bg-dark-800 border border-dark-700 rounded-2xl text-white placeholder-dark-600 focus:outline-none focus:border-nvidia/50 transition-all focus:ring-4 focus:ring-nvidia/5"
                                    />
                                </div>
                            </div>

                            {/* Email (only for registration) */}
                            {isRegistering && (
                                <div className="space-y-2">
                                    <label className="text-sm font-medium text-dark-300 ml-1">Email Address</label>
                                    <div className="relative">
                                        <ShieldCheckIcon className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-dark-500" />
                                        <input
                                            type="email"
                                            value={email}
                                            onChange={(e) => setEmail(e.target.value)}
                                            placeholder="Enter your email"
                                            required={isRegistering}
                                            className="w-full pl-12 pr-4 py-3.5 bg-dark-800 border border-dark-700 rounded-2xl text-white placeholder-dark-600 focus:outline-none focus:border-nvidia/50 transition-all focus:ring-4 focus:ring-nvidia/5"
                                        />
                                    </div>
                                </div>
                            )}

                            {/* Password */}
                            <div className="space-y-2">
                                <div className="flex items-center justify-between ml-1">
                                    <label className="text-sm font-medium text-dark-300">Password</label>
                                    {!isRegistering && (
                                        <button type="button" className="text-xs text-dark-500 hover:text-nvidia transition-colors">
                                            Forgot password?
                                        </button>
                                    )}
                                </div>
                                <div className="relative">
                                    <KeyIcon className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-dark-500" />
                                    <input
                                        type="password"
                                        value={password}
                                        onChange={(e) => setPassword(e.target.value)}
                                        placeholder="Enter your password"
                                        required
                                        className="w-full pl-12 pr-4 py-3.5 bg-dark-800 border border-dark-700 rounded-2xl text-white placeholder-dark-600 focus:outline-none focus:border-nvidia/50 transition-all focus:ring-4 focus:ring-nvidia/5"
                                    />
                                </div>
                            </div>
                        </div>

                        <button
                            type="submit"
                            disabled={isLoading}
                            className="w-full py-4 bg-nvidia hover:bg-nvidia-dark text-white font-bold rounded-2xl transition-all relative overflow-hidden group shadow-lg shadow-nvidia/20"
                        >
                            <div className="relative z-10 flex items-center justify-center gap-2">
                                {isLoading ? (
                                    <ArrowPathIcon className="w-5 h-5 animate-spin" />
                                ) : (
                                    <>
                                        <span>{isRegistering ? 'Sign Up' : 'Sign In'}</span>
                                        <ArrowRightIcon className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
                                    </>
                                )}
                            </div>
                        </button>
                    </form>

                    <div className="mt-8 text-center">
                        <p className="text-dark-500">
                            {isRegistering ? 'Already have an account?' : "Don't have an account?"}{' '}
                            <button
                                type="button"
                                onClick={() => setIsRegistering(!isRegistering)}
                                className="text-nvidia font-bold hover:underline"
                            >
                                {isRegistering ? 'Sign In' : 'Create One'}
                            </button>
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
}
