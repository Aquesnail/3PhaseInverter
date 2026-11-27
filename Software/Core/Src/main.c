/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"
#include "adc.h"
#include "dma.h"
#include "fdcan.h"
#include "hrtim.h"
#include "tim.h"
#include "usart.h"
#include "gpio.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */

/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/

/* USER CODE BEGIN PV */
/* ================= minimal interrupt chain (no control algorithm) =============
 * ADC1+ADC2 (dual regular simultaneous, 2 conversions each) -> DMA1_Channel1
 *   DMA moves one 32-bit word per conversion from ADC12_COMMON->CDR:
 *     [15:0] = ADC1 result, [31:16] = ADC2 result
 * ADC3 (independent, 2 conversions) -> DMA1_Channel2  (this one has the NVIC line)
 * Both are triggered by HRTIM ADC trigger 1, so every trigger produces one
 * complete set of six phase samples (voltage + current).
 *
 * Two measurement windows for the logic analyzer (both pins are push-pull
 * outputs created by MX_GPIO_Init):
 *   PD7 : 50 kHz fast loop  (one pulse per HRTIM trigger)
 *   PB5 : slow loop         (one pulse per TIM1 update interrupt)
 * The actual computation is replaced by a tunable busy-wait Dummy_Delay().
 * -------------------------------------------------------------------------- */
#include "tim.h"                       /* htim1 */

extern DMA_HandleTypeDef hdma_adc3;    /* defined in adc.c */

#define FAST_PIN        GPIO_PIN_7     /* PD7: 50 kHz fast-loop window */
#define FAST_PORT       GPIOD
#define SLOW_PIN        GPIO_PIN_5     /* PB5: slow-loop window        */
#define SLOW_PORT       GPIOB

/* dummy workload length, in loop iterations (~6 CPU cycles each at -O0).
 * Tune live from the debugger, no rebuild needed. */
volatile uint32_t g_fast_loops = 150u;   /* 20 us slot  -> keep well below */
volatile uint32_t g_slow_loops = 300u;

volatile uint32_t g_fast_count = 0u;    /* 50 kHz ticks  */
volatile uint32_t g_slow_count = 0u;    /* TIM1 ticks    */
volatile uint32_t g_main_loops = 0u;    /* main-loop heartbeat */

volatile uint32_t g_adc12_raw[2] = {0u, 0u};  /* {ADC1,ADC2} of conv #1 / #2 */
volatile uint16_t g_adc3_raw[2]  = {0u, 0u};  /* ADC3 conv #1 / #2           */

static uint32_t s_buf12[2];            /* DMA target: 2 x 32-bit (CDR)  */
static uint16_t s_buf3[2];             /* DMA target: 2 x 16-bit        */

/* CubeMX currently has ADC "DMA Continuous Requests" = DISABLE for ADC1/ADC2/ADC3.
 * With DMACFG = 0 the hardware clears ADSTART at the end of every DMA transfer,
 * so the ADC converts one sequence and then stops. Until that option is enabled
 * in CubeMX, re-arm ADSTART once per tick (runtime workaround, no config change).
 * Set to 0 as soon as CubeMX enables DMAContinuousRequests. */
#ifndef ADC_DMACFG_WORKAROUND
#define ADC_DMACFG_WORKAROUND 0   /* CubeMX: DMAContinuousRequests = ENABLE now */
#endif
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
/* USER CODE BEGIN PFP */

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */
/* Busy-wait used as a stand-in for the control computation.
 * Volatile counter => the compiler cannot remove it. */
static void Dummy_Delay(uint32_t n)
{
  while (n-- > 0u)
  {
    __NOP();
  }
}

/* ---- IRQ handlers: CubeMX IRQ-handler generation is disabled, so the vectors
 * we use are provided here explicitly. ---- */
void DMA1_Channel2_IRQHandler(void)          /* ADC3 DMA done: 50 kHz tick */
{
  HAL_DMA_IRQHandler(&hdma_adc3);
}

void TIM1_UP_TIM16_IRQHandler(void)          /* TIM1 update: slow-loop tick */
{
  HAL_TIM_IRQHandler(&htim1);
}

/* Slow loop: TIM1 update interrupt -> PB5 window + dummy workload */
void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *htim)
{
  if (htim->Instance == TIM1)
  {
    SLOW_PORT->BSRR = SLOW_PIN;                     /* PB5 high */

    Dummy_Delay(g_slow_loops);

    SLOW_PORT->BSRR = (uint32_t)SLOW_PIN << 16u;    /* PB5 low  */
    g_slow_count++;
  }
}

/* Fast loop: one HRTIM trigger worth of samples -> PD7 window + dummy workload */
void HAL_ADC_ConvCpltCallback(ADC_HandleTypeDef *hadc)
{
  if (hadc->Instance == ADC3)
  {
    FAST_PORT->BSRR = FAST_PIN;                     /* PD7 high */

    Dummy_Delay(g_fast_loops);

    FAST_PORT->BSRR = (uint32_t)FAST_PIN << 16u;    /* PD7 low  */

    g_adc12_raw[0] = s_buf12[0];
    g_adc12_raw[1] = s_buf12[1];
    g_adc3_raw[0]  = s_buf3[0];
    g_adc3_raw[1]  = s_buf3[1];

    g_fast_count++;

#if (ADC_DMACFG_WORKAROUND != 0)
    /* re-arm both ADC sequences so the next HRTIM trigger converts again */
    SET_BIT(ADC1->CR, ADC_CR_ADSTART);               /* ADC1 + ADC2 (dual)     */
    SET_BIT(ADC3->CR, ADC_CR_ADSTART);               /* ADC3                   */
#endif
  }
}
/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_DMA_Init();
  MX_ADC1_Init();
  MX_ADC2_Init();
  MX_ADC3_Init();
  MX_HRTIM1_Init();
  MX_FDCAN1_Init();
  MX_USART2_UART_Init();
  MX_ADC4_Init();
  MX_ADC5_Init();
  MX_USART3_UART_Init();
  MX_TIM1_Init();
  /* USER CODE BEGIN 2 */
  /* ---- HRTIM: start the counters (ADC trigger comes from MASTER CMP1).
   * The PWM outputs are started too, but with the current CubeMX settings they
   * have no Set/Reset source, so they stay at their idle level (= no switching,
   * safe while the power stage is not ready).                       ---- */
  /* The HRTIM ADC trigger register (ADC1R) is double buffered: it only becomes
   * active after an update event of its configured update source. With the
   * current CubeMX settings no update event is generated (MISR.MUPD never sets),
   * so the ADC trigger would never be armed. Force one software update here. */
  if (HAL_HRTIM_SoftwareUpdate(&hhrtim1, HRTIM_TIMERUPDATE_MASTER) != HAL_OK)
  {
    Error_Handler();
  }

  if (HAL_HRTIM_WaveformCountStart(&hhrtim1,
                                   HRTIM_TIMERID_MASTER | HRTIM_TIMERID_TIMER_A |
                                   HRTIM_TIMERID_TIMER_E | HRTIM_TIMERID_TIMER_F) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_HRTIM_WaveformOutputStart(&hhrtim1,
                                    HRTIM_OUTPUT_TA1 | HRTIM_OUTPUT_TA2 |
                                    HRTIM_OUTPUT_TE1 | HRTIM_OUTPUT_TE2 |
                                    HRTIM_OUTPUT_TF1 | HRTIM_OUTPUT_TF2) != HAL_OK)
  {
    Error_Handler();
  }

  /* ---- TIM1: slow-loop interrupt source.
   * Use HAL_TIM_Base_Start_IT() (sets DIER.UIE = update interrupt); the PWM
   * variant would raise the CC interrupt instead of the update one.
   * The TIM1 update NVIC line is now generated by CubeMX in tim.c, so nothing
   * is configured here.
   * NOTE: Prescaler=9 / Period=17999 with a 170 MHz timer clock = 944 Hz.
   * For exactly 1 kHz use Period=16999 (Prescaler=9).                   ---- */
  if (HAL_TIM_Base_Start_IT(&htim1) != HAL_OK)
  {
    Error_Handler();
  }

  /* ---- ADC: calibrate (differential channels) then start both DMA chains ---- */
  if (HAL_ADCEx_Calibration_Start(&hadc1, ADC_DIFFERENTIAL_ENDED) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_ADCEx_Calibration_Start(&hadc3, ADC_DIFFERENTIAL_ENDED) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_ADCEx_MultiModeStart_DMA(&hadc1, s_buf12, 2u) != HAL_OK)   /* ADC1 + ADC2 */
  {
    Error_Handler();
  }
  if (HAL_ADC_Start_DMA(&hadc3, (uint32_t *)s_buf3, 2u) != HAL_OK)   /* ADC3        */
  {
    Error_Handler();
  }
  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
    g_main_loops++;
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Configure the main internal regulator output voltage
  */
  HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1_BOOST);

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSI;
  RCC_OscInitStruct.PLL.PLLM = RCC_PLLM_DIV4;
  RCC_OscInitStruct.PLL.PLLN = 85;
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV2;
  RCC_OscInitStruct.PLL.PLLQ = RCC_PLLQ_DIV2;
  RCC_OscInitStruct.PLL.PLLR = RCC_PLLR_DIV2;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_4) != HAL_OK)
  {
    Error_Handler();
  }
}

/* USER CODE BEGIN 4 */

/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
