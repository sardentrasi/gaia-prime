import re
import os

path = r'c:\Project\demeter\templates\growth_log.html'
with open(path, 'r', encoding='utf-8') as f:
    h = f.read()

fetch_logic = '''
    const growthList = document.getElementById('growth-list');
    async function fetchHistory() {
        if(!growthList) return;
        try {
            const res = await fetch('/api/growth-logs');
            const data = await res.json();
            
            if (data.length === 0) {
                growthList.innerHTML = '<p class="text-center py-12 text-[14px] font-medium text-[#888888]">No logs yet.</p>';
                return;
            }

            growthList.innerHTML = '';
            data.forEach(log => {
                const card = document.createElement('div');
                card.className = 'relative pl-12 mb-4';
                
                let badgeClass = 'bg-brand-green-light/30 border-brand-green-light text-brand-green-deep';
                if (log.health !== 'Excellent' && log.health !== 'Good') {
                    badgeClass = 'bg-warn-amber/10 border-warn-amber/20 text-warn-amber';
                }

                card.innerHTML = `
                    <div class="absolute left-[13px] top-4 w-2 h-2 rounded-full bg-brand-green-deep z-10 ring-4 ring-pure-white"></div>
                    <div class="bg-pure-white rounded-lg border border-border-subtle p-md shadow-[0_2px_8px_rgba(0,0,0,0.03)] hover:border-border-medium transition-colors">
                        <div class="flex justify-between items-start mb-4">
                            <div>
                                <span class="font-mono-code text-[14px] text-near-black font-semibold mr-2">${log.plant_name}</span>
                                <span class="font-mono-code text-mono-code text-gray-500">${log.timestamp}</span>
                            </div>
                            <span class="px-2 py-1 bg-surface-container-low rounded-full font-mono-code text-mono-code text-primary">Server-Logged</span>
                        </div>
                        <div class="flex gap-4 mb-4">
                            <div class="flex-1 bg-surface-container-lowest border border-border-subtle rounded-md p-3 text-center">
                                <span class="block font-mono-code text-mono-code text-gray-500 mb-1">Height</span>
                                <span class="font-card-title text-card-title text-near-black">${log.height} cm</span>
                            </div>
                            <div class="flex-1 border rounded-md p-3 text-center ${badgeClass}">
                                <span class="block font-mono-code text-mono-code mb-1">Health</span>
                                <span class="font-card-title text-card-title">${log.health}</span>
                            </div>
                        </div>
                        <div class="bg-gray-50 rounded-md p-4 border border-border-subtle">
                            <div class="flex items-center gap-2 mb-2">
                                <span class="material-symbols-outlined text-brand-green-deep text-sm" data-icon="psychiatry">psychiatry</span>
                                <span class="font-label-uppercase text-label-uppercase text-near-black">Report Notes</span>
                            </div>
                            <p class="font-body-base text-body-base text-gray-700">${log.notes || 'No description provided.'}</p>
                        </div>
                    </div>
                `;
                growthList.appendChild(card);
            });
            if(typeof lucide !== 'undefined') lucide.createIcons();
        } catch (e) { console.error(e); }
    }
    fetchHistory();
'''

if 'const growthList' not in h:
    h = h.replace('if(chatForm) {', fetch_logic + '\n\n    if(chatForm) {')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(h)
    print('History fetch embedded')
else:
    print('Already embedded.')
