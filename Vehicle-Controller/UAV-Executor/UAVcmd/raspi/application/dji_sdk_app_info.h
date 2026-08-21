/**
 ********************************************************************
 * @file    dji_sdk_app_info.h
 * @brief   This is the header file for defining the structure and (exported) function prototypes.
 *
 * @copyright (c) 2018 DJI. All rights reserved.
 *
 * All information contained herein is, and remains, the property of DJI.
 * The intellectual and technical concepts contained herein are proprietary
 * to DJI and may be covered by U.S. and foreign patents, patents in process,
 * and protected by trade secret or copyright law.  Dissemination of this
 * information, including but not limited to data and other proprietary
 * material(s) incorporated within the information, in any form, is strictly
 * prohibited without the express written consent of DJI.
 *
 * If you receive this source code without DJI’s authorization, you may not
 * further disseminate the information, and you must immediately remove the
 * source code and notify DJI of its removal. DJI reserves the right to pursue
 * legal actions against you for any loss(es) or damage(s) caused by your
 * failure to do so.
 *
 *********************************************************************
 */

/* Define to prevent recursive inclusion -------------------------------------*/
#ifndef DJI_SDK_APP_INFO_H
#define DJI_SDK_APP_INFO_H

/* Includes ------------------------------------------------------------------*/

#ifdef __cplusplus
extern "C" {
#endif

/* Exported constants --------------------------------------------------------*/
/*
 * Create a Payload SDK application at:
 * https://developer.dji.com/user/apps/#all
 *
 * Replace these placeholders only in the private deployment workspace.
 * Never commit real DJI application credentials to source control.
 */
#define USER_APP_NAME               "YOUR_DJI_PSDK_APP_NAME"
#define USER_APP_ID                 "YOUR_DJI_PSDK_APP_ID"
#define USER_APP_KEY                "YOUR_DJI_PSDK_APP_KEY"
#define USER_APP_LICENSE            "YOUR_DJI_PSDK_APP_LICENSE"
#define USER_DEVELOPER_ACCOUNT      "YOUR_DJI_DEVELOPER_ACCOUNT"
#define USER_BAUD_RATE              "460800"

/* Exported types ------------------------------------------------------------*/

/* Exported functions --------------------------------------------------------*/


#ifdef __cplusplus
}
#endif

#endif // DJI_SDK_APP_INFO_H
/************************ (C) COPYRIGHT DJI Innovations *******END OF FILE******/
