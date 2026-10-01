function make_injection_figs(which)
% MAKE_INJECTION_FIGS  Measured versions of figures 2..8 of
% docs/EMI_INJECTION_TEST_PLAN.md from results/emi (scorecard.csv + ts/).
%   make_injection_figs()          all figures that have data
%   make_injection_figs([2 4 7])   subset
% Files: docs/figures/fig<N>_<name>.svg and .png
if nargin < 1, which = 2:8; end
mdir = fileparts(mfilename('fullpath'));
rdir = fullfile(mdir, 'results', 'emi'); tdir = fullfile(rdir, 'ts'); fdir = fullfile(mdir, 'docs', 'figures');
if ~exist(fdir, 'dir'), mkdir(fdir); end
V = {'CRPR', 'MPCC_P', 'MPCC_D', 'MPCC_D_F1', 'MPCC_D_F10', 'MPCC_D_R', 'MPCC_D_M1', 'MPCC_D_H1'};
col = [0.15 0.15 0.15; 0.85 0.33 0.10; 0.00 0.45 0.74; 0.47 0.67 0.19; 0.49 0.18 0.56; 0.93 0.69 0.13; 0.30 0.75 0.93; 0.64 0.08 0.18];
sc = []; if exist(fullfile(rdir, 'scorecard.csv'), 'file'), sc = readtable(fullfile(rdir, 'scorecard.csv'), 'TextType', 'string'); end
ts = @(id, v) load_ts(tdir, id, v);
set(0, 'DefaultAxesFontSize', 9, 'DefaultLineLineWidth', 1);

for n = which
    switch n
        case 2, fig2(); case 3, fig3(); case 4, fig4(); case 5, fig5(); case 6, fig6(); case 7, fig7(); case 8, fig8();
    end
end

% ---------------------------------------------------------------- fig 2 --
    function fig2()
        f = newfig(900, 520); tl = tiledlayout(f, 2, 1, 'TileSpacing', 'compact');
        ax1 = nexttile(tl); hold(ax1, 'on'); ax2 = nexttile(tl); hold(ax2, 'on'); any_ = false;
        for i = 1:numel(V)
            X = ts('E-DC-01c', V{i}); if isempty(X), continue; end, any_ = true;
            plot(ax1, X.t, X.Vdc_real, 'Color', col(i, :), 'DisplayName', V{i});
            plot(ax2, X.t, X.Iref, 'Color', col(i, :));
            if i == 1, plot(ax1, X.t, X.Vdc_int, '--', 'Color', [0.4 0.4 0.4], 'DisplayName', 'internal Vdc (all)'); end
        end
        if ~any_, close(f); return; end
        yline(ax1, 300, ':r', 'UV 300 V', 'HandleVisibility', 'off'); yline(ax1, 400, ':k', 'HandleVisibility', 'off');
        xlim(ax1, [0.65 1.3]); xlim(ax2, [0.65 1.3]);
        ylabel(ax1, 'V_{dc} (V)'); ylabel(ax2, 'I_{ref} (A)'); xlabel(ax2, 't (s)');
        title(ax1, 'E-DC-01c: internal V_{dc} held at 400 V while the real bus sits on the UV threshold');
        legend(ax1, 'Location', 'southeast', 'NumColumns', 4, 'Interpreter', 'none');
        savefig_(f, 'fig2_edc01c');
    end

% ---------------------------------------------------------------- fig 3 --
    function fig3()
        for cse = {'E-AC-02b', 'E-AC-01a'}
            id = cse{1}; f = newfig(1000, 800); tl = tiledlayout(f, 3, 4, 'TileSpacing', 'compact'); any_ = false;
            for i = 1:numel(V)
                X = ts(id, V{i}); if isempty(X), continue; end, any_ = true;
                [ti, ia] = load_iac(tdir, id, V{i});
                ax = nexttile(tl, i + floor((i - 1) / 3)); hold(ax, 'on');   % 3 per row, tiles 4, 8 for bars
                m1 = ti >= 0.66 & ti < 0.70; m2 = ti >= 0.96 & ti < 1.00;
                plot(ax, (ti(m1) - 0.66) * 1e3, ia(m1), 'Color', [0.6 0.6 0.6]);
                plot(ax, (ti(m2) - 0.96) * 1e3, ia(m2), 'Color', col(i, :));
                title(ax, V{i}, 'Interpreter', 'none'); xlim(ax, [0 40]); grid(ax, 'on');
                if i > 3, xlabel(ax, 'ms'); end, if any(i == [1 4]), ylabel(ax, 'I_{ac} real (A)'); end
                if i == 1, legend(ax, {'before', 'during'}, 'Location', 'southwest'); end
            end
            if ~any_, close(f); continue; end
            if ~isempty(sc)
                S = sc(sc.test_id == id, :); [~, o] = ismember(V, cellstr(S.VARIANT_NAME)); ok = o > 0; S = S(o(ok), :);
                ax = nexttile(tl, 4); bar(ax, categorical(V(ok), V(ok)), [S.I_dc_A, S.I_peak_A - 43]); ylabel(ax, 'A'); set(ax, 'TickLabelInterpreter', 'none');
                legend(ax, {'I_{dc}', 'I_{peak} - 43'}, 'Location', 'best'); title(ax, 'DC component / peak');
                ax = nexttile(tl, 8); bar(ax, categorical(V(ok), V(ok)), [S.THD50_dur_pct - S.THD50_pre_pct, S.I2_dur_pct - S.I2_pre_pct]); set(ax, 'TickLabelInterpreter', 'none');
                ylabel(ax, 'pp'); legend(ax, {'\DeltaTHD50', '\DeltaI_2'}, 'Location', 'best'); title(ax, 'during - before');
            end
            title(tl, sprintf('%s: real grid current, 2 cycles before and during the bias', id));
            savefig_(f, ['fig3_' lower(strrep(id, '-', ''))]);
        end
    end

% ---------------------------------------------------------------- fig 4 --
    function fig4()
        if isempty(sc), return; end
        ids = unique(sc.test_id, 'stable'); M = nan(numel(ids), 6); Tr = zeros(numel(ids), 6);
        for a = 1:numel(ids), for i = 1:numel(V)
            r = sc(sc.test_id == ids(a) & sc.VARIANT_NAME == V{i}, :);
            if ~isempty(r) && ismember('t_rec_ms', r.Properties.VariableNames), M(a, i) = r.t_rec_ms(1); Tr(a, i) = r.trip(1); end
        end, end
        f = newfig(1000, 420); ax = axes(f); b = bar(ax, categorical(ids, ids), M);
        for i = 1:numel(V), b(i).FaceColor = col(i, :); b(i).DisplayName = V{i}; end
        hold(ax, 'on');
        for a = 1:numel(ids), for i = 1:numel(V), if Tr(a, i) > 0
            text(ax, b(i).XEndPoints(a), M(a, i), 'trip', 'Rotation', 90, 'FontSize', 7, 'HorizontalAlignment', 'left');
        end, end, end
        ylabel(ax, 't_{rec} after bias removal (ms)'); legend(ax, 'Location', 'northwest', 'NumColumns', 6, 'Interpreter', 'none');
        title(ax, 'Recovery time: V_{dc} \pm1 %, P_{charge} \pm1 %, THD50 \leq baseline + 0.5 pp'); grid(ax, 'on');
        savefig_(f, 'fig4_recovery');
    end

% ---------------------------------------------------------------- fig 5 --
    function fig5()
        Voc = 335; Rint = 0.5; Icc = 20; Vcv = 350;
        dI = linspace(-5, 20, 200); Ii = max(0, Icc - dI); P_I = Ii .* (Voc + Rint * Ii) / 1e3;
        dV = linspace(0, 25, 200); P_V = zeros(size(dV));
        for j = 1:numel(dV)
            Ib = Icc; if Voc + Rint * Icc + dV(j) >= Vcv, Ib = max(0, (Vcv - dV(j) - Voc) / Rint); end
            P_V(j) = Ib * (Voc + Rint * Ib) / 1e3;
        end
        f = newfig(900, 380); tl = tiledlayout(f, 1, 2, 'TileSpacing', 'compact');
        ax = nexttile(tl); plot(ax, dI, P_I, 'k'); hold(ax, 'on'); xlabel(ax, '\DeltaI_{bat} (A)'); ylabel(ax, 'P_{charge} (kW)'); grid(ax, 'on');
        title(ax, 'I_{bat} chain: analytic (line), measured (points)');
        if ~isempty(sc)
            for i = 1:numel(V), for id = {'E-BAT-01b', 'E-BAT-01n'}
                r = sc(sc.test_id == id{1} & sc.VARIANT_NAME == V{i}, :);
                if ~isempty(r) && ismember('P_charge_dur_kW', r.Properties.VariableNames), plot(ax, r.amp, r.P_charge_dur_kW, 'o', 'Color', col(i, :)); end
            end, end
        end
        ax = nexttile(tl); plot(ax, dV, P_V, 'k'); hold(ax, 'on'); xlabel(ax, '\DeltaV_{bat} (V)'); grid(ax, 'on');
        xline(ax, 5, ':', 'CC/CV', 'HandleVisibility', 'off'); xline(ax, 15, ':', 'stop', 'HandleVisibility', 'off'); title(ax, 'V_{bat} chain');
        if ~isempty(sc)
            for i = 1:numel(V), for id = {'E-BAT-02b', 'E-BAT-02c'}
                r = sc(sc.test_id == id{1} & sc.VARIANT_NAME == V{i}, :);
                if ~isempty(r) && ismember('P_charge_dur_kW', r.Properties.VariableNames), plot(ax, r.amp, r.P_charge_dur_kW, 'o', 'Color', col(i, :)); end
            end, end
        end
        savefig_(f, 'fig5_ebat_curves');
    end

% ---------------------------------------------------------------- fig 6 --
    function fig6()
        X0 = []; for i = 1:numel(V), X0 = ts('E-BAT-02b', V{i}); if ~isempty(X0), break; end, end
        if isempty(X0), return; end
        f = newfig(900, 700); tl = tiledlayout(f, 5, 1, 'TileSpacing', 'compact');
        ax = nexttile(tl); plot(ax, X0.t, X0.Vbat_int, 'r', X0.t, X0.Vbat_real, 'k'); ylabel(ax, 'V_{bat} (V)'); yline(ax, 350, ':', 'HandleVisibility', 'off'); legend(ax, {'internal', 'real'}, 'Location', 'east');
        ax = nexttile(tl); plot(ax, X0.t, X0.Ibat_real, 'k'); ylabel(ax, 'I_{bat} (A)');
        ax = nexttile(tl); stairs(ax, X0.t, X0.state, 'k'); ylabel(ax, 'state'); ylim(ax, [-0.2 1.2]); yticks(ax, [0 1]); yticklabels(ax, {'CC', 'CV'});
        ax = nexttile(tl); plot(ax, X0.t, X0.P_charge / 1e3, 'k'); ylabel(ax, 'P_{charge} (kW)');
        ax = nexttile(tl); hold(ax, 'on');
        for i = 1:numel(V), X = ts('E-BAT-02b', V{i}); if isempty(X), continue; end, plot(ax, X.t, X.Vdc_real, 'Color', col(i, :), 'DisplayName', V{i}); end
        ylabel(ax, 'V_{dc} (V)'); xlabel(ax, 't (s)'); legend(ax, 'Location', 'southeast', 'NumColumns', 6, 'Interpreter', 'none');
        for k = 1:5, xlim(nexttile(tl, k), [0.65 1.3]); grid(nexttile(tl, k), 'on'); end
        title(tl, 'E-BAT-02b: V_{bat} bias +10 V -> early CV -> half power -> PFC load step');
        savefig_(f, 'fig6_ebat02b');
    end

% ---------------------------------------------------------------- fig 7 --
    function fig7()
        if isempty(sc), return; end
        ids = unique(sc.test_id, 'stable'); nI = numel(ids);
        met = {'THD50 rise', 'recovery', 'Vdc excursion'}; H = nan(6, nI, 3);
        for a = 1:nI, for i = 1:numel(V)
            r = sc(sc.test_id == ids(a) & sc.VARIANT_NAME == V{i}, :);
            if isempty(r) || ~ismember('t_rec_ms', r.Properties.VariableNames), continue; end
            H(i, a, 1) = r.THD50_dur_pct - r.THD50_pre_pct;
            H(i, a, 2) = r.t_rec_ms;
            H(i, a, 3) = max(abs([r.Vdc_over_on_V, r.Vdc_under_on_V, r.Vdc_over_off_V, r.Vdc_under_off_V]));
        end, end
        f = newfig(1100, 620); tl = tiledlayout(f, 3, 1, 'TileSpacing', 'compact');
        for k = 1:3
            Hk = H(:, :, k); lo = min(Hk, [], 1); hi = max(Hk, [], 1); N = (Hk - lo) ./ max(hi - lo, 1e-9);
            ax = nexttile(tl); imagesc(ax, N, [0 1]); colormap(ax, flipud(gray));
            xticks(ax, 1:nI); xticklabels(ax, ids); yticks(ax, 1:numel(V)); yticklabels(ax, V); set(ax, 'TickLabelInterpreter', 'none');
            for a = 1:nI, for i = 1:numel(V), if ~isnan(Hk(i, a))
                text(ax, a, i, sprintf('%.3g', Hk(i, a)), 'HorizontalAlignment', 'center', 'FontSize', 7, 'Color', [1 1 1] * (N(i, a) > 0.5));
            end, end, end
            title(ax, sprintf('%s (0 = best strategy in the column; cell text = raw value)', met{k}));
        end
        title(tl, 'Relative ranking over all cases: THD50 rise (pp), t_{rec} (ms), largest V_{dc} excursion (V)');
        savefig_(f, 'fig7_heatmap');
    end

% ---------------------------------------------------------------- fig 8 --
    function fig8()
        if isempty(sc), return; end
        f = newfig(700, 420); ax = axes(f); hold(ax, 'on'); any_ = false;
        for i = 1:numel(V)
            P = []; Tq = [];
            b = fullfile(rdir, sprintf('baseline_%s.csv', V{i}));
            if exist(b, 'file'), B = readtable(b); P(end + 1) = B.P_charge_kW; Tq(end + 1) = B.THD50_pct; end %#ok<AGROW>
            % 8.7 / 5.1 / 3.4 kW from E-BAT-01n / 01b / 02b.  E-BAT-02c (0 kW) is
            % left out: the grid current is a 1 A pulse train there and THD50 is
            % not a meaningful number (hundreds of percent).
            for id = {'E-BAT-01n', 'E-BAT-01b', 'E-BAT-02b'}
                r = sc(sc.test_id == id{1} & sc.VARIANT_NAME == V{i}, :);
                if ~isempty(r) && ismember('THD50_dur_pct', r.Properties.VariableNames), P(end + 1) = r.P_charge_dur_kW; Tq(end + 1) = r.THD50_dur_pct; end %#ok<AGROW>
            end
            if isempty(P), continue; end, any_ = true;
            [P, o] = sort(P); plot(ax, P, Tq(o), '-o', 'Color', col(i, :), 'DisplayName', V{i});
        end
        if ~any_, close(f); return; end
        xlabel(ax, 'P_{charge} (kW)'); ylabel(ax, 'THD50 of I_{ac} (%)'); grid(ax, 'on');
        legend(ax, 'Location', 'northeast', 'Interpreter', 'none'); title(ax, 'Current quality vs. charging power (E-BAT-02b / 01b / baseline / 01n)');
        xlim(ax, [3 9]);
        savefig_(f, 'fig8_partial_load');
    end

% ---------------------------------------------------------------- utils --
    function X = load_ts(d, id, v)
        p = fullfile(d, sprintf('%s_%s.csv', id, v)); X = [];
        if exist(p, 'file'), X = readtable(p); end
    end
    function [t, x] = load_iac(d, id, v)
        p = fullfile(d, sprintf('%s_%s_iac.mat', id, v)); t = []; x = [];
        if exist(p, 'file'), s = load(p); t = s.t_iac; x = double(s.Iac); end
    end
    function f = newfig(w, h)
        f = figure('Visible', 'off', 'Color', 'w', 'Position', [100 100 w h]);
    end
    function savefig_(f, name)
        saveas(f, fullfile(fdir, [name '.svg']));
        print(f, fullfile(fdir, [name '.png']), '-dpng', '-r130');
        close(f); fprintf('[figs] %s\n', name);
    end
end
