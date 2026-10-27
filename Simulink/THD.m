%% ============================================================
%  a_signal 的 FFT 与 THD 分析脚本（安全版）
%  绝不清理工作区，绝不删除任何变量
%  数据获取顺序：a_signal -> out -> a_signal_backup.mat
% ============================================================

clc;            % 只清命令行
close all;      % 只关旧图
% 注意：此处不写 clear / clear all / clearvars，保护工作区数据

%% ---------- 0. 获取数据（多来源自动兜底） ----------
if ~exist('a_signal', 'var')
    if exist('out', 'var')
        try
            a_signal = out.get('a_signal');
            fprintf('已从 out 对象提取 a_signal。\n');
        catch
            try
                a_signal = out.a_signal;
                fprintf('已从 out 对象提取 a_signal。\n');
            catch
                error('out 对象中找不到 a_signal，请检查 To Workspace 变量名。');
            end
        end
    elseif exist('a_signal_backup.mat', 'file')
        load('a_signal_backup.mat');
        fprintf('已从 a_signal_backup.mat 恢复 a_signal。\n');
    else
        error(['工作区没有 a_signal，也找不到 out 或 a_signal_backup.mat。', ...
               '请先运行仿真，或手动 load 备份文件。']);
    end
end

%% ---------- 1. 参数设置 ----------
fundamental_freq = 50;      % 基波频率 (Hz)，60Hz 系统改成 60
t_start = [];               % 分析起始时间，[] 表示自动取后 50% 数据
t_end   = [];               % 分析结束时间，[] 表示到数据末尾
max_harmonic = 50;          % 最大谐波次数
window_type = 'hanning';    % 窗函数：'hanning' 或 'none'

%% ---------- 2. 提取时间与信号 ----------
[t, y] = extractSignal(a_signal);

% 确保为列向量
t = t(:);
y = y(:);

% 多列数据只取第一列
if size(y, 2) > 1
    y = y(:, 1);
    warning('a_signal 包含多列数据，仅分析第一列。');
end

%% ---------- 3. 计算采样率 ----------
dt = diff(t);
Fs = 1 / median(dt);
fprintf('采样率 Fs = %.2f Hz\n', Fs);

%% ---------- 4. 截取稳态段 ----------
if isempty(t_start)
    t_start = t(1) + 0.5 * (t(end) - t(1));   % 默认取后一半
end
if isempty(t_end)
    t_end = t(end);
end

idx = (t >= t_start) & (t <= t_end);
t = t(idx);
y = y(idx);

if length(y) < 10
    error('截取后的数据点太少，请检查 t_start / t_end 设置。');
end

%% ---------- 5. 去直流分量 ----------
y = y - mean(y);

%% ---------- 6. 加窗与 FFT ----------
N = length(y);

if strcmpi(window_type, 'hanning')
    % 手动生成 Hanning 窗，不依赖任何工具箱
    n = (0:N-1)';
    win = 0.5 * (1 - cos(2*pi*n/(N-1)));
else
    win = ones(N, 1);
end
y_win = y .* win;
Y = fft(y_win);

% 单边幅值谱（考虑窗增益修正）
P2 = abs(Y) / sum(win);
P1 = P2(1:floor(N/2) + 1);
P1(2:end-1) = 2 * P1(2:end-1);
f = Fs * (0:floor(N/2)) / N;

%% ---------- 7. 确定基波频率与幅值 ----------
if isempty(fundamental_freq)
    % 自动检测：在 10 Hz 以上找最大谱峰
    valid_idx = f > 10;
    [~, idx_max] = max(P1(valid_idx));
    f_valid = f(valid_idx);
    fundamental_freq = f_valid(idx_max);
    fprintf('自动检测基波频率：%.2f Hz\n', fundamental_freq);
else
    fprintf('使用指定基波频率：%.2f Hz\n', fundamental_freq);
end

[~, idx_f0] = min(abs(f - fundamental_freq));
A1 = P1(idx_f0);    % 基波幅值

%% ---------- 8. 手动 FFT 计算 THD ----------
max_h = min(max_harmonic, floor((Fs/2) / fundamental_freq));
harmonic_orders = 2:max_h;
harmonic_mags = zeros(size(harmonic_orders));
thd_sum = 0;

for k = harmonic_orders
    fh = k * fundamental_freq;
    [~, idx_h] = min(abs(f - fh));
    Ah = P1(idx_h);
    harmonic_mags(k - 1) = Ah;
    thd_sum = thd_sum + Ah^2;
end

THD_percent = sqrt(thd_sum) / A1 * 100;

%% ---------- 9. 内置 thd 函数验证（若有工具箱） ----------
THD_builtin = NaN;
try
    THD_builtin = thd(y, Fs) * 100;   % 需要 Signal Processing Toolbox
catch
    warning('未找到 thd 函数（Signal Processing Toolbox），仅使用手动计算结果。');
end

%% ---------- 10. 绘图 ----------
figure('Name', 'a_signal FFT & THD 分析', 'Color', 'w');

% 时域波形
subplot(2, 1, 1);
plot(t, y, 'b');
xlabel('Time (s)');
ylabel('Amplitude');
title('时域波形（稳态段）');
grid on;

% 频域幅值谱
subplot(2, 1, 2);
stem(f, P1, 'Marker', 'none', 'Color', [0.2 0.2 0.8]);
hold on;

% 标注基波
plot(fundamental_freq, A1, 'ro', 'MarkerFaceColor', 'r', 'MarkerSize', 8);
text(fundamental_freq, A1, sprintf(' 基波 %.1f Hz', fundamental_freq), ...
    'VerticalAlignment', 'bottom', 'Color', 'r');

% 标注谐波
for k = harmonic_orders
    fh = k * fundamental_freq;
    if fh > Fs/2
        break;
    end
    [~, idx_h] = min(abs(f - fh));
    plot(fh, P1(idx_h), 'go', 'MarkerFaceColor', 'g', 'MarkerSize', 5);
end

xlabel('Frequency (Hz)');
ylabel('Magnitude');
title(sprintf('FFT 频谱  (THD = %.2f%%)', THD_percent));
xlim([0, min(Fs/2, max(10 * fundamental_freq, 1000))]);
grid on;
legend('幅值谱', '基波', '谐波', 'Location', 'northeast');

%% ---------- 11. 打印结果 ----------
fprintf('\n========== 分析结果 ==========\n');
fprintf('基波频率        : %.2f Hz\n', fundamental_freq);
fprintf('基波幅值        : %.6f\n', A1);
fprintf('THD（手动 FFT） : %.4f %%\n', THD_percent);
if ~isnan(THD_builtin)
    fprintf('THD（内置 thd） : %.4f %%\n', THD_builtin);
end
fprintf('各次谐波幅值：\n');
for k = harmonic_orders
    if (k - 1) <= length(harmonic_mags)
        fprintf('  %2d 次 (%6.1f Hz) : %.6f\n', ...
            k, k * fundamental_freq, harmonic_mags(k - 1));
    end
end
fprintf('==============================\n');

%% ============================================================
%  辅助函数：从不同格式中提取时间与信号
% ============================================================
function [t, y] = extractSignal(sig)
    if isa(sig, 'timeseries')
        t = sig.Time;
        y = sig.Data;

    elseif isstruct(sig) && isfield(sig, 'time') && isfield(sig, 'signals')
        % Simulink To Workspace: Structure with time
        t = sig.time;
        y = sig.signals.values;

    elseif isstruct(sig) && isfield(sig, 'Time') && isfield(sig, 'Data')
        % 某些版本 timeseries 结构形式
        t = sig.Time;
        y = sig.Data;

    elseif isnumeric(sig)
        if size(sig, 2) >= 2
            t = sig(:, 1);
            y = sig(:, 2);
        else
            error(['a_signal 只有一列数据，无法确定时间。', ...
                   '请提供包含时间与信号的两列数组，', ...
                   '或使用 timeseries / Structure with time 格式。']);
        end

    else
        error('无法识别的 a_signal 格式，请检查变量类型。');
    end
end