import React from 'react';

type Props = {
    label: string;
    value: number;
};

const QualityBadge: React.FC<Props> = ({ label, value }) => {
    // Determine color based on score (0 to 1)
    const getColors = (val: number) => {
        if (val >= 0.85) return "bg-green-500/10 text-green-500 border-green-500/20";
        if (val >= 0.7) return "bg-yellow-500/10 text-yellow-500 border-yellow-500/20";
        return "bg-red-500/10 text-red-500 border-red-500/20";
    };

    return (
        <div className={`flex items-center gap-2 px-2 py-0.5 rounded-full border text-[10px] uppercase tracking-wider font-bold ${getColors(value)}`}>
            <span className="opacity-70">{label}:</span>
            <span>{(value * 100).toFixed(0)}%</span>
        </div>
    );
};

export default QualityBadge;
