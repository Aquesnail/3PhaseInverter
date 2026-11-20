function [v_alpha_ref, v_beta_ref, P_filt, Q_filt, w_out, breaker_cmd] = Droop_Control_Sync( ...
    v_cap_alpha,  v_cap_beta,  ... % 【输入1】逆变器输出电容侧电压 (αβ 坐标系)
    i_inv_alpha,  i_inv_beta,  ... % 【输入2】逆变器输出侧网侧/负载电流 (αβ 坐标系)
    v_grid_alpha, v_grid_beta, ... % 【输入3】外部主电网侧母线电压 (αβ 坐标系)
    w0, E0, mp, nq, wc, Ts)
%#codegen
% =========================================================================
% 输入说明:
%   v_cap_alpha, v_cap_beta   : [输出电容侧] 逆变器 LC 滤波电容两端电压 (V)
%   i_inv_alpha, i_inv_beta   : [输出电容侧] 流向断路器/负载的输出电流 (A)
%   v_grid_alpha, v_grid_beta : [外部电网侧] 三相断路器外侧电网母线电压 (V)
%   w0, E0                    : 额定角频率 (rad/s) 与额定相电压幅值 (V)
%   mp, nq                    : 有功/无功下垂系数
%   wc                        : 功率低通滤波截止角频率 (rad/s)
%   Ts                        : 控制步长 (s)
% 输出说明:
%   v_alpha_ref, v_beta_ref   : QPR 电压内环参考电压 (αβ 轴)
%   P_filt, Q_filt            : 滤波后的有功/无功功率
%   f_out                     : 逆变器当前输出频率 (Hz)
%   breaker_cmd               : 三相断路器合闸指令 (3x1 向量: [cmd_a; cmd_b; cmd_c])
%                               0 = 断开 (未同步/离网), 1 = 合闸导通 (同步完成)
% =========================================================================

%% 内部状态保持
persistent P_prev Q_prev theta_prev
persistent sync_integ sync_ok_counter is_breaker_closed

if isempty(P_prev)
    P_prev = 0;
    Q_prev = 0;
    theta_prev = 0;
    sync_integ = 0;
    sync_ok_counter = 0;
    is_breaker_closed = false;
end

%% 1. 瞬时功率计算 (基于输出电容侧电压与输出电流)
p_inst = 1.5 * (v_cap_alpha * i_inv_alpha + v_cap_beta * i_inv_beta);
q_inst = 1.5 * (v_cap_beta * i_inv_alpha - v_cap_alpha * i_inv_beta);

%% 2. 功率一阶低通滤波
alpha = (wc * Ts) / (1 + wc * Ts);
P_filt = (1 - alpha) * P_prev + alpha * p_inst;
Q_filt = (1 - alpha) * Q_prev + alpha * q_inst;
P_prev = P_filt;
Q_prev = Q_filt;

% 3. Independent inverter: presynchronization and closure disabled.
w_sync = 0;
E_sync = 0;

%% 4. 下垂方程叠加与参考频率/幅值生成
% 频率计算 (并网前叠加上 w_sync 进行调相；并网后 w_sync 归零，由 -mp*P 维持功角自同步)
w_out = (w0 - mp * P_filt) + w_sync;

% 幅值计算 (并网前叠加上 E_sync 消除压差；并网后回归标准下垂)
E_out = (E0 - nq * Q_filt) + E_sync;

% 基础安全限幅
if E_out < 0.8 * E0
    E_out = 0.8 * E0;
elseif E_out > 1.2 * E0
    E_out = 1.2 * E0;
end

%% 5. 相角自累加积分
theta = theta_prev + w_out * Ts;
if theta >= 2 * pi
    theta = theta - 2 * pi;
elseif theta < 0
    theta = theta + 2 * pi;
end
theta_prev = theta;

%% 6. 合成 αβ 轴参考电压 (送入 QPR 电压内环)
v_alpha_ref = E_out * cos(theta);
v_beta_ref  = E_out * sin(theta);

%% 7. 组装三相断路器动作信号
if is_breaker_closed
    % 准同期条件满足，输出合闸指令 (给 1 触发导通/合闸)
    breaker_cmd = [0; 0; 0];
else
    % 预同步中或离网状态，保持断开
    breaker_cmd = [1; 1; 1];
end

end